from __future__ import annotations

import json
from dataclasses import dataclass, field
from fnmatch import fnmatch
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TypeVar

from loushang.coding.loader.types import (
    ExtensionDescriptor,
    PackageResourceSummary,
    PromptFragmentDescriptor,
    ResourceBundle,
    ResourceDiagnostic,
    ResourceMergeDecision,
    ResourceSnapshot,
    ResourceSourceKind,
    SkillDescriptor,
    ThemeDescriptor,
)
from loushang.coding.package.source import PackageSourceConfig
from loushang.resource.frontmatter import FrontmatterParseError, parse_frontmatter

BUILT_IN_RESOURCE_PACKAGE = "loushang.coding.resources"
_MAX_SKILL_NAME_LENGTH = 64
_MAX_SKILL_DESCRIPTION_LENGTH = 1024
_IGNORE_FILE_NAMES = (".gitignore", ".ignore", ".fdignore")
_CONTEXT_FILE_NAMES = ("AGENTS.md", "AGENTS.MD", "CLAUDE.md", "CLAUDE.MD")
_DEFAULT_USER_RESOURCE_ROOT = Path.home() / ".loushang"
_SOURCE_PRIORITY: dict[ResourceSourceKind, int] = {
    "temporary": -1,
    "project_local": 0,
    "user_global": 1,
    "external_package": 2,
    "built_in": 3,
}
_SOURCE_SCOPE = {
    "built_in": "builtin",
    "external_package": "package",
    "project_local": "project",
    "user_global": "user",
    "temporary": "temporary",
}
_SOURCE_LABEL = {
    "built_in": "package_resource",
    "external_package": "package_resource",
    "project_local": "filesystem",
    "user_global": "filesystem",
    "temporary": "filesystem",
}

DescriptorT = TypeVar("DescriptorT", PromptFragmentDescriptor, SkillDescriptor, ExtensionDescriptor, ThemeDescriptor)


@dataclass(frozen=True)
class _SourceDiscovery:
    prompts: list[PromptFragmentDescriptor] = field(default_factory=list)
    skills: list[SkillDescriptor] = field(default_factory=list)
    extensions: list[ExtensionDescriptor] = field(default_factory=list)
    themes: list[ThemeDescriptor] = field(default_factory=list)
    diagnostics: list[ResourceDiagnostic] = field(default_factory=list)


class DefaultResourceLoader:
    def __init__(
        self,
        package_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
        package_source_filters: dict[str | Path, PackageSourceConfig] | None = None,
        user_resource_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_extension_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_skill_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_prompt_template_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_theme_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        no_extensions: bool = False,
        no_skills: bool = False,
        no_prompt_templates: bool = False,
        no_themes: bool = False,
        no_context_files: bool = False,
        system_prompt: str | None = None,
        append_system_prompt: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self._snapshot: ResourceSnapshot | None = None
        self._package_roots = _normalize_package_roots(package_roots)
        self._package_source_filters = _normalize_package_source_filters(package_source_filters)
        self._user_resource_roots = _normalize_user_resource_roots(user_resource_roots)
        self._explicit_user_resource_roots: set[Path] = set()
        self._additional_extension_paths = _normalize_runtime_paths(additional_extension_paths)
        self._additional_skill_paths = _normalize_runtime_paths(additional_skill_paths)
        self._additional_prompt_template_paths = _normalize_runtime_paths(additional_prompt_template_paths)
        self._additional_theme_paths = _normalize_runtime_paths(additional_theme_paths)
        self._no_extensions = bool(no_extensions)
        self._no_skills = bool(no_skills)
        self._no_prompt_templates = bool(no_prompt_templates)
        self._no_themes = bool(no_themes)
        self._no_context_files = bool(no_context_files)
        self._system_prompt_source = system_prompt
        self._append_system_prompt_sources = tuple(append_system_prompt or ())
        self._resolved_system_prompt: str | None = None
        self._resolved_append_system_prompt: tuple[str, ...] = ()

    def set_package_roots(
        self,
        package_roots: list[str | Path] | tuple[str | Path, ...] | None,
        package_source_filters: dict[str | Path, PackageSourceConfig] | None = None,
    ) -> None:
        self._package_roots = _normalize_package_roots(package_roots)
        self._package_source_filters = _normalize_package_source_filters(package_source_filters)

    def set_user_resource_roots(
        self,
        user_resource_roots: list[str | Path] | tuple[str | Path, ...] | None,
        *,
        explicit_roots: list[str | Path] | tuple[str | Path, ...] | set[str] | None = None,
    ) -> None:
        self._user_resource_roots = _normalize_user_resource_roots(user_resource_roots)
        self._explicit_user_resource_roots = set(_normalize_user_resource_roots(tuple(explicit_roots) if explicit_roots is not None else None))

    def set_runtime_options(
        self,
        *,
        additional_extension_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_skill_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_prompt_template_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_theme_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        no_extensions: bool | None = None,
        no_skills: bool | None = None,
        no_prompt_templates: bool | None = None,
        no_themes: bool | None = None,
        no_context_files: bool | None = None,
        system_prompt: str | None = None,
        append_system_prompt: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        if additional_extension_paths is not None:
            self._additional_extension_paths = _normalize_runtime_paths(additional_extension_paths)
        if additional_skill_paths is not None:
            self._additional_skill_paths = _normalize_runtime_paths(additional_skill_paths)
        if additional_prompt_template_paths is not None:
            self._additional_prompt_template_paths = _normalize_runtime_paths(additional_prompt_template_paths)
        if additional_theme_paths is not None:
            self._additional_theme_paths = _normalize_runtime_paths(additional_theme_paths)
        if no_extensions is not None:
            self._no_extensions = bool(no_extensions)
        if no_skills is not None:
            self._no_skills = bool(no_skills)
        if no_prompt_templates is not None:
            self._no_prompt_templates = bool(no_prompt_templates)
        if no_themes is not None:
            self._no_themes = bool(no_themes)
        if no_context_files is not None:
            self._no_context_files = bool(no_context_files)
        self._system_prompt_source = system_prompt
        self._append_system_prompt_sources = tuple(append_system_prompt or ())

    def discover_resources(self, cwd: str | Path) -> ResourceBundle:
        snapshot = _discover_snapshot(
            Path(cwd),
            package_roots=self._package_roots,
            package_source_filters=self._package_source_filters,
            user_resource_roots=self._user_resource_roots,
            explicit_user_roots=self._explicit_user_resource_roots,
            additional_extension_paths=self._additional_extension_paths,
            additional_skill_paths=self._additional_skill_paths,
            additional_prompt_template_paths=self._additional_prompt_template_paths,
            additional_theme_paths=self._additional_theme_paths,
            no_extensions=self._no_extensions,
            no_skills=self._no_skills,
            no_prompt_templates=self._no_prompt_templates,
            no_themes=self._no_themes,
            no_context_files=self._no_context_files,
        )
        self._snapshot = snapshot
        self._resolved_system_prompt = _resolve_prompt_input(self._system_prompt_source, cwd=Path(cwd))
        self._resolved_append_system_prompt = tuple(
            resolved
            for source in self._append_system_prompt_sources
            if (resolved := _resolve_prompt_input(source, cwd=Path(cwd))) is not None
        )
        return snapshot.to_bundle()

    def reload_resources(self, cwd: str | Path | None = None) -> ResourceBundle:
        if cwd is not None:
            return self.discover_resources(cwd)
        if self._snapshot is None:
            return self.discover_resources(Path.cwd())
        return self.discover_resources(self._snapshot.cwd)

    def get_resource_bundle(self) -> ResourceBundle:
        return self.get_resource_snapshot().to_bundle()

    def get_resource_snapshot(self) -> ResourceSnapshot:
        if self._snapshot is None:
            return ResourceSnapshot(
                cwd=Path.cwd(),
                source_kinds=_source_kinds_for(
                    self._package_roots,
                    self._user_resource_roots,
                    has_temporary=any(
                        (
                            self._additional_extension_paths,
                            self._additional_skill_paths,
                            self._additional_prompt_template_paths,
                            self._additional_theme_paths,
                        )
                    ),
                ),
            )
        return self._snapshot

    def get_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self.get_resource_snapshot().diagnostics)

    def get_resource_diagnostics(
        self,
        *,
        source_kind: ResourceSourceKind | None = None,
        resource_type: str | None = None,
        code: str | None = None,
    ) -> list[ResourceDiagnostic]:
        diagnostics = list(self.get_resource_snapshot().diagnostics)
        if source_kind is not None:
            diagnostics = [diagnostic for diagnostic in diagnostics if diagnostic.source_kind == source_kind]
        if resource_type is not None:
            diagnostics = [diagnostic for diagnostic in diagnostics if diagnostic.resource_type == resource_type]
        if code is not None:
            diagnostics = [diagnostic for diagnostic in diagnostics if diagnostic.code == code]
        return diagnostics

    def get_package_resource_summaries(self) -> list[PackageResourceSummary]:
        snapshot = self.get_resource_snapshot()
        summaries: list[PackageResourceSummary] = []
        for root in self._package_roots:
            summaries.append(
                PackageResourceSummary(
                    source_root=root,
                    prompt_count=_count_package_descriptors(snapshot.candidate_prompt_descriptors, root),
                    skill_count=_count_package_descriptors(snapshot.candidate_skill_descriptors, root),
                    extension_count=_count_package_descriptors(snapshot.candidate_extension_descriptors, root),
                    theme_count=_count_package_descriptors(snapshot.candidate_theme_descriptors, root),
                    diagnostic_count=_count_package_diagnostics(snapshot.diagnostics, root),
                )
            )
        return summaries

    def get_skills(self) -> list[SkillDescriptor]:
        return list(self.get_resource_snapshot().active_skill_descriptors)

    def get_prompts(self) -> dict[str, object]:
        bundle = self.get_resource_bundle()
        return {
            "agents_md": bundle.agents_md,
            "prompt_fragments": list(bundle.prompt_fragments),
            "prompt_descriptors": list(bundle.prompt_descriptors),
            "prompts": list(bundle.prompts),
        }

    def get_agents_files(self) -> dict[str, object]:
        bundle = self.get_resource_bundle()
        context_descriptors = [
            descriptor
            for descriptor in bundle.prompt_descriptors
            if descriptor.prompt_kind in {"agents_md", "claude_md"}
        ]
        return {
            "agents_files": [
                {"path": str(descriptor.source_path), "content": descriptor.text}
                for descriptor in context_descriptors
            ]
        }

    def get_append_system_prompt(self) -> list[str]:
        return list(self.get_resource_bundle().prompt_fragments)

    def get_system_prompt_override(self) -> str | None:
        return self._resolved_system_prompt

    def get_append_system_prompt_overrides(self) -> list[str]:
        return list(self._resolved_append_system_prompt)

    def get_system_prompt(self, *, base_prompt: str | None = None) -> str | None:
        from loushang.coding.prompt import assemble_system_prompt

        system_prompt = assemble_system_prompt(base_prompt=base_prompt, resource_bundle=self.get_resource_bundle())
        return system_prompt or None

    def get_extensions(self) -> list[ExtensionDescriptor]:
        return list(self.get_resource_snapshot().active_extension_descriptors)


def _discover_snapshot(
    cwd: Path,
    *,
    package_roots: tuple[Path, ...] = (),
    package_source_filters: dict[Path, PackageSourceConfig] | None = None,
    user_resource_roots: tuple[Path, ...] = (),
    explicit_user_roots: set[Path] | None = None,
    additional_extension_paths: tuple[Path, ...] = (),
    additional_skill_paths: tuple[Path, ...] = (),
    additional_prompt_template_paths: tuple[Path, ...] = (),
    additional_theme_paths: tuple[Path, ...] = (),
    no_extensions: bool = False,
    no_skills: bool = False,
    no_prompt_templates: bool = False,
    no_themes: bool = False,
    no_context_files: bool = False,
) -> ResourceSnapshot:
    target = Path(cwd)
    if no_context_files:
        context_descriptors, agents_descriptor, context_diagnostics = [], None, []
    else:
        context_descriptors, agents_descriptor, context_diagnostics = _discover_context_descriptors(
            target,
            user_resource_roots=user_resource_roots,
        )
    project_context_descriptors = [
        descriptor for descriptor in context_descriptors if descriptor.source_kind == "project_local"
    ]
    project_root = (
        project_context_descriptors[-1].source_path.parent
        if project_context_descriptors
        else (target if target.is_dir() else target.parent)
    )

    built_in = _apply_resource_switches(
        _discover_built_in_resources(),
        no_prompts=no_prompt_templates,
        no_skills=no_skills,
        no_extensions=no_extensions,
        no_themes=no_themes,
    )
    external = _apply_resource_switches(
        _discover_external_package_resources(package_roots, package_source_filters=package_source_filters),
        no_prompts=no_prompt_templates,
        no_skills=no_skills,
        no_extensions=no_extensions,
        no_themes=no_themes,
    )
    user_global = _apply_resource_switches(
        _discover_user_global_resources(user_resource_roots, explicit_roots=explicit_user_roots),
        no_prompts=no_prompt_templates,
        no_skills=no_skills,
        no_extensions=no_extensions,
        no_themes=no_themes,
    )
    project = _apply_resource_switches(
        _discover_project_resources(project_root),
        no_prompts=no_prompt_templates,
        no_skills=no_skills,
        no_extensions=no_extensions,
        no_themes=no_themes,
    )
    temporary = _discover_temporary_resources(
        target,
        extension_paths=additional_extension_paths,
        skill_paths=additional_skill_paths,
        prompt_paths=additional_prompt_template_paths,
        theme_paths=additional_theme_paths,
    )

    active_prompts, prompt_diagnostics, prompt_decisions = _resolve_strict_named_candidates(
        [*temporary.prompts, *built_in.prompts, *external.prompts, *user_global.prompts, *project.prompts],
        resource_type="prompt",
    )
    active_skills, skill_diagnostics, skill_decisions = _resolve_strict_named_candidates(
        [*temporary.skills, *built_in.skills, *external.skills, *user_global.skills, *project.skills],
        resource_type="skill",
    )
    active_extensions, extension_diagnostics, extension_decisions = _resolve_extension_candidates(
        [*temporary.extensions, *built_in.extensions, *external.extensions, *user_global.extensions, *project.extensions],
        resource_type="extension",
    )
    active_themes, theme_diagnostics, theme_decisions = _resolve_candidates(
        [*temporary.themes, *built_in.themes, *external.themes, *user_global.themes, *project.themes],
        resource_type="theme",
    )

    diagnostics = [
        *context_diagnostics,
        *built_in.diagnostics,
        *external.diagnostics,
        *user_global.diagnostics,
        *project.diagnostics,
        *temporary.diagnostics,
        *prompt_diagnostics,
        *skill_diagnostics,
        *extension_diagnostics,
        *theme_diagnostics,
    ]
    merge_decisions = [
        *prompt_decisions,
        *skill_decisions,
        *extension_decisions,
        *theme_decisions,
    ]
    return ResourceSnapshot(
        cwd=target,
        source_kinds=_source_kinds_for(
            package_roots,
            user_resource_roots,
            has_temporary=any(
                (
                    additional_extension_paths,
                    additional_skill_paths,
                    additional_prompt_template_paths,
                    additional_theme_paths,
                )
            ),
        ),
        active_agents_descriptor=agents_descriptor,
        active_context_descriptors=tuple(context_descriptors),
        candidate_agents_descriptors=tuple(context_descriptors),
        active_prompt_descriptors=tuple(active_prompts),
        candidate_prompt_descriptors=tuple([*temporary.prompts, *built_in.prompts, *external.prompts, *user_global.prompts, *project.prompts]),
        active_skill_descriptors=tuple(active_skills),
        candidate_skill_descriptors=tuple([*temporary.skills, *built_in.skills, *external.skills, *user_global.skills, *project.skills]),
        active_extension_descriptors=tuple(active_extensions),
        candidate_extension_descriptors=tuple([*temporary.extensions, *built_in.extensions, *external.extensions, *user_global.extensions, *project.extensions]),
        active_theme_descriptors=tuple(active_themes),
        candidate_theme_descriptors=tuple([*temporary.themes, *built_in.themes, *external.themes, *user_global.themes, *project.themes]),
        diagnostics=tuple(diagnostics),
        merge_decisions=tuple(merge_decisions),
    )


def _discover_user_global_resources(
    user_resource_roots: tuple[Path, ...],
    *,
    explicit_roots: set[Path] | None = None,
) -> _SourceDiscovery:
    prompts: list[PromptFragmentDescriptor] = []
    skills: list[SkillDescriptor] = []
    extensions: list[ExtensionDescriptor] = []
    themes: list[ThemeDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    explicit = explicit_roots or set()

    for index, root in enumerate(user_resource_roots):
        if not root.exists():
            if root in explicit:
                diagnostics.append(
                    ResourceDiagnostic(
                        code="missing_user_resource_root",
                        message=f"User resource root does not exist: {root}",
                        source_path=root,
                        resource_type="package",
                        source_kind="user_global",
                        metadata={"root": str(root)},
                    )
                )
            continue
        if not root.is_dir():
            if root in explicit:
                diagnostics.append(
                    ResourceDiagnostic(
                        code="invalid_user_resource_root",
                        message=f"User resource root must be a directory: {root}",
                        source_path=root,
                        resource_type="package",
                        source_kind="user_global",
                        metadata={"root": str(root)},
                    )
                )
            continue
        user_prompts, prompt_diagnostics = _discover_prompts_from_dir(
            root / "prompts",
            source_kind="user_global",
            source_scope="user",
            source_label=_SOURCE_LABEL["user_global"],
            source_root_order=index,
        )
        user_skills, skill_diagnostics = _discover_skills_from_dir(
            root / "skills",
            source_kind="user_global",
            source_scope="user",
            source_label=_SOURCE_LABEL["user_global"],
            source_root_order=index,
        )
        user_extensions, extension_diagnostics = _discover_extensions_from_dir(
            root / "extensions",
            source_kind="user_global",
            source_scope="user",
            source_label=_SOURCE_LABEL["user_global"],
            source_root_order=index,
        )
        user_themes, theme_diagnostics = _discover_themes_from_dir(
            root / "themes",
            source_kind="user_global",
            source_scope="user",
            source_label=_SOURCE_LABEL["user_global"],
            source_root_order=index,
        )
        prompts.extend(user_prompts)
        skills.extend(user_skills)
        extensions.extend(user_extensions)
        themes.extend(user_themes)
        diagnostics.extend([*prompt_diagnostics, *skill_diagnostics, *extension_diagnostics, *theme_diagnostics])

    return _SourceDiscovery(
        prompts=prompts,
        skills=skills,
        extensions=extensions,
        themes=themes,
        diagnostics=diagnostics,
    )


def _discover_project_resources(root: Path) -> _SourceDiscovery:
    prompts, prompt_diagnostics = _discover_prompts(root)
    skills, skill_diagnostics = _discover_skills(root)
    extensions, extension_diagnostics = _discover_extensions(root)
    themes, theme_diagnostics = _discover_themes(root)
    return _SourceDiscovery(
        prompts=prompts,
        skills=skills,
        extensions=extensions,
        themes=themes,
        diagnostics=[
            *prompt_diagnostics,
            *skill_diagnostics,
            *extension_diagnostics,
            *theme_diagnostics,
        ],
    )


def _discover_external_package_resources(
    package_roots: tuple[Path, ...],
    *,
    package_source_filters: dict[Path, PackageSourceConfig] | None = None,
) -> _SourceDiscovery:
    prompts: list[PromptFragmentDescriptor] = []
    skills: list[SkillDescriptor] = []
    extensions: list[ExtensionDescriptor] = []
    themes: list[ThemeDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []

    for index, root in enumerate(package_roots):
        if not root.exists():
            diagnostics.append(_package_root_diagnostic("missing_package_root", "Package root does not exist.", root))
            continue
        if not root.is_dir():
            diagnostics.append(_package_root_diagnostic("invalid_package_root", "Package root must be a directory.", root))
            continue
        package_prompts, prompt_diagnostics = _discover_prompts_from_dir(
            root / "prompts",
            source_kind="external_package",
            source_scope="package",
            source_label=_SOURCE_LABEL["external_package"],
            source_root_order=index,
        )
        package_skills, skill_diagnostics = _discover_skills_from_dir(
            root / "skills",
            source_kind="external_package",
            source_scope="package",
            source_label=_SOURCE_LABEL["external_package"],
            source_root_order=index,
        )
        package_extensions, extension_diagnostics = _discover_extensions_from_dir(
            root / "extensions",
            source_kind="external_package",
            source_scope="package",
            source_label=_SOURCE_LABEL["external_package"],
            source_root_order=index,
        )
        package_themes, theme_diagnostics = _discover_themes_from_dir(
            root / "themes",
            source_kind="external_package",
            source_scope="package",
            source_label=_SOURCE_LABEL["external_package"],
            source_root_order=index,
        )
        package_filter = (package_source_filters or {}).get(root)
        if package_filter is not None:
            package_prompts = _filter_package_descriptors(package_prompts, root=root, patterns=package_filter.prompts)
            package_skills = _filter_package_descriptors(package_skills, root=root, patterns=package_filter.skills)
            package_extensions = _filter_package_descriptors(package_extensions, root=root, patterns=package_filter.extensions)
            package_themes = _filter_package_descriptors(package_themes, root=root, patterns=package_filter.themes)
        prompts.extend(package_prompts)
        skills.extend(package_skills)
        extensions.extend(package_extensions)
        themes.extend(package_themes)
        package_diagnostics = [
            *prompt_diagnostics,
            *skill_diagnostics,
            *extension_diagnostics,
            *theme_diagnostics,
        ]
        diagnostics.extend(package_diagnostics)
        if not package_prompts and not package_skills and not package_extensions and not package_themes and not package_diagnostics:
            diagnostics.append(_package_root_diagnostic("empty_package_root", "Package root contains no loadable resources.", root))

    return _SourceDiscovery(
        prompts=prompts,
        skills=skills,
        extensions=extensions,
        themes=themes,
        diagnostics=diagnostics,
    )


def _apply_resource_switches(
    discovery: _SourceDiscovery,
    *,
    no_prompts: bool,
    no_skills: bool,
    no_extensions: bool,
    no_themes: bool,
) -> _SourceDiscovery:
    return _SourceDiscovery(
        prompts=[] if no_prompts else discovery.prompts,
        skills=[] if no_skills else discovery.skills,
        extensions=[] if no_extensions else discovery.extensions,
        themes=[] if no_themes else discovery.themes,
        diagnostics=discovery.diagnostics,
    )


def _discover_temporary_resources(
    cwd: Path,
    *,
    extension_paths: tuple[Path, ...],
    skill_paths: tuple[Path, ...],
    prompt_paths: tuple[Path, ...],
    theme_paths: tuple[Path, ...],
) -> _SourceDiscovery:
    prompts: list[PromptFragmentDescriptor] = []
    skills: list[SkillDescriptor] = []
    extensions: list[ExtensionDescriptor] = []
    themes: list[ThemeDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []

    for index, raw_path in enumerate(prompt_paths):
        loaded, loaded_diagnostics = _discover_temporary_prompts_from_path(_resolve_runtime_path(raw_path, cwd), index)
        prompts.extend(loaded)
        diagnostics.extend(loaded_diagnostics)
    for index, raw_path in enumerate(skill_paths):
        loaded, loaded_diagnostics = _discover_temporary_skills_from_path(_resolve_runtime_path(raw_path, cwd), index)
        skills.extend(loaded)
        diagnostics.extend(loaded_diagnostics)
    for index, raw_path in enumerate(extension_paths):
        loaded, loaded_diagnostics = _discover_temporary_extensions_from_path(_resolve_runtime_path(raw_path, cwd), index)
        extensions.extend(loaded)
        diagnostics.extend(loaded_diagnostics)
    for index, raw_path in enumerate(theme_paths):
        loaded, loaded_diagnostics = _discover_temporary_themes_from_path(_resolve_runtime_path(raw_path, cwd), index)
        themes.extend(loaded)
        diagnostics.extend(loaded_diagnostics)

    return _SourceDiscovery(
        prompts=prompts,
        skills=skills,
        extensions=extensions,
        themes=themes,
        diagnostics=diagnostics,
    )


def _discover_temporary_prompts_from_path(
    path: Path,
    source_root_order: int,
) -> tuple[list[PromptFragmentDescriptor], list[ResourceDiagnostic]]:
    if not path.exists():
        return [], [_temporary_missing_path_diagnostic(path, resource_type="prompt")]
    if path.is_file():
        if path.suffix != ".md":
            return [], [_temporary_unsupported_path_diagnostic(path, resource_type="prompt", message="Prompt template paths must be .md files or directories.")]
        text, diagnostics = _read_text_file(
            path,
            diagnostic_code="unreadable_prompt_entry",
            message_prefix="Failed to read prompt entry",
        )
        if text is None:
            return [], diagnostics
        descriptor, frontmatter_diagnostics = _prompt_descriptor_from_text(
            name=path.stem,
            source_path=path,
            text=text,
            canonical_name=path.name,
            source_kind="temporary",
            source_scope="temporary",
            source=_SOURCE_LABEL["temporary"],
            source_root=path.parent,
            source_root_order=source_root_order,
        )
        diagnostics.extend(frontmatter_diagnostics)
        return ([descriptor] if descriptor is not None else []), diagnostics
    return _discover_prompts_from_dir(
        path,
        source_kind="temporary",
        source_scope="temporary",
        source_label=_SOURCE_LABEL["temporary"],
        source_root_order=source_root_order,
    )


def _discover_temporary_skills_from_path(
    path: Path,
    source_root_order: int,
) -> tuple[list[SkillDescriptor], list[ResourceDiagnostic]]:
    if not path.exists():
        return [], [_temporary_missing_path_diagnostic(path, resource_type="skill")]
    if path.is_file():
        if path.name != "SKILL.md":
            return [], [_temporary_unsupported_path_diagnostic(path, resource_type="skill", message="Skill paths must be SKILL.md files or directories.")]
        descriptor, diagnostics = _skill_descriptor_from_file(
            path,
            root_dir=path.parent,
            parent_name=path.parent.name,
            source_kind="temporary",
            source_scope="temporary",
            source_label=_SOURCE_LABEL["temporary"],
            source_root_order=source_root_order,
        )
        return ([descriptor] if descriptor is not None else []), diagnostics
    if (path / "SKILL.md").is_file():
        descriptor, diagnostics = _skill_descriptor_from_file(
            path / "SKILL.md",
            root_dir=path,
            parent_name=path.name,
            source_kind="temporary",
            source_scope="temporary",
            source_label=_SOURCE_LABEL["temporary"],
            source_root_order=source_root_order,
        )
        return ([descriptor] if descriptor is not None else []), diagnostics
    return _discover_skills_from_dir(
        path,
        source_kind="temporary",
        source_scope="temporary",
        source_label=_SOURCE_LABEL["temporary"],
        source_root_order=source_root_order,
    )


def _discover_temporary_extensions_from_path(
    path: Path,
    source_root_order: int,
) -> tuple[list[ExtensionDescriptor], list[ResourceDiagnostic]]:
    if not path.exists():
        return [], [_temporary_missing_path_diagnostic(path, resource_type="extension")]
    if path.is_file():
        if path.suffix != ".py":
            return [], [_temporary_unsupported_path_diagnostic(path, resource_type="extension", message="Extension paths must be .py files or directories.")]
        return [
            ExtensionDescriptor(
                name=path.stem,
                source_path=path,
                entry_path=path,
                canonical_name=path.name,
                source_kind="temporary",
                source_scope="temporary",
                source=_SOURCE_LABEL["temporary"],
                source_root=path.parent,
                source_root_order=source_root_order,
            )
        ], []
    entry_path = _find_extension_entry(path)
    if entry_path is not None:
        return [
            ExtensionDescriptor(
                name=path.name,
                source_path=path,
                entry_path=entry_path,
                canonical_name=path.name,
                source_kind="temporary",
                source_scope="temporary",
                source=_SOURCE_LABEL["temporary"],
                source_root=path,
                source_root_order=source_root_order,
            )
        ], []
    return _discover_extensions_from_dir(
        path,
        source_kind="temporary",
        source_scope="temporary",
        source_label=_SOURCE_LABEL["temporary"],
        source_root_order=source_root_order,
    )


def _discover_temporary_themes_from_path(
    path: Path,
    source_root_order: int,
) -> tuple[list[ThemeDescriptor], list[ResourceDiagnostic]]:
    if not path.exists():
        return [], [_temporary_missing_path_diagnostic(path, resource_type="theme")]
    if path.is_file():
        if path.suffix != ".json":
            return [], [_temporary_unsupported_path_diagnostic(path, resource_type="theme", message="Theme paths must be .json files or directories.")]
        diagnostic = _theme_json_diagnostic(path, source_kind="temporary")
        if diagnostic is not None:
            return [], [diagnostic]
        return [
            ThemeDescriptor(
                name=path.stem,
                source_path=path,
                canonical_name=path.name,
                source_kind="temporary",
                source_scope="temporary",
                source=_SOURCE_LABEL["temporary"],
                source_root=path.parent,
                source_root_order=source_root_order,
            )
        ], []
    return _discover_themes_from_dir(
        path,
        source_kind="temporary",
        source_scope="temporary",
        source_label=_SOURCE_LABEL["temporary"],
        source_root_order=source_root_order,
    )


def _temporary_missing_path_diagnostic(path: Path, *, resource_type: str) -> ResourceDiagnostic:
    return ResourceDiagnostic(
        code=f"missing_{resource_type}_path",
        message=f"{resource_type.title()} path does not exist: {path}",
        source_path=path,
        resource_type=resource_type,
        source_kind="temporary",
        metadata={"path": str(path)},
    )


def _temporary_unsupported_path_diagnostic(path: Path, *, resource_type: str, message: str) -> ResourceDiagnostic:
    return ResourceDiagnostic(
        code=f"unsupported_{resource_type}_path",
        message=message,
        source_path=path,
        resource_type=resource_type,
        source_kind="temporary",
        metadata={"path": str(path)},
    )


def _discover_built_in_resources() -> _SourceDiscovery:
    prompts, prompt_diagnostics = _discover_built_in_prompts()
    skills, skill_diagnostics = _discover_built_in_skills()
    extensions, extension_diagnostics = _discover_built_in_extensions()
    themes, theme_diagnostics = _discover_built_in_themes()
    return _SourceDiscovery(
        prompts=prompts,
        skills=skills,
        extensions=extensions,
        themes=themes,
        diagnostics=[
            *prompt_diagnostics,
            *skill_diagnostics,
            *extension_diagnostics,
            *theme_diagnostics,
        ],
    )


def _discover_context_descriptors(
    start: Path,
    *,
    user_resource_roots: tuple[Path, ...],
) -> tuple[list[PromptFragmentDescriptor], PromptFragmentDescriptor | None, list[ResourceDiagnostic]]:
    descriptors: list[PromptFragmentDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []

    for index, root in enumerate(user_resource_roots):
        if not root.is_dir():
            continue
        descriptor, read_diagnostics = _discover_context_descriptor_from_dir(
            root,
            source_kind="user_global",
            source_root_order=index,
        )
        diagnostics.extend(read_diagnostics)
        if descriptor is not None:
            descriptors.append(descriptor)

    project_descriptors: list[PromptFragmentDescriptor] = []
    for index, current in enumerate(reversed(_ancestor_dirs(start))):
        descriptor, read_diagnostics = _discover_context_descriptor_from_dir(
            current,
            source_kind="project_local",
            source_root_order=index,
        )
        diagnostics.extend(read_diagnostics)
        if descriptor is not None:
            project_descriptors.append(descriptor)
    descriptors.extend(project_descriptors)
    return descriptors, _nearest_context_descriptor(descriptors), diagnostics


def _ancestor_dirs(start: Path) -> list[Path]:
    current = start if start.is_dir() else start.parent
    dirs: list[Path] = []
    while True:
        dirs.append(current)
        if current.parent == current:
            return dirs
        current = current.parent


def _discover_context_descriptor_from_dir(
    root: Path,
    *,
    source_kind: ResourceSourceKind,
    source_root_order: int,
) -> tuple[PromptFragmentDescriptor | None, list[ResourceDiagnostic]]:
    for filename in _CONTEXT_FILE_NAMES:
        candidate = root / filename
        if not candidate.is_file():
            continue
        text, diagnostics = _read_text_file(
            candidate,
            diagnostic_code=_context_read_diagnostic_code(candidate.name),
            message_prefix=f"Failed to read {candidate.name}",
        )
        if text is None:
            return None, diagnostics
        return (
            PromptFragmentDescriptor(
                name=candidate.name,
                source_path=candidate,
                text=text,
                id=_context_descriptor_id(candidate.name, source_kind),
                canonical_name=candidate.name,
                prompt_kind=_context_prompt_kind(candidate.name),
                source_kind=source_kind,
                source_scope=_SOURCE_SCOPE[source_kind],
                source=_SOURCE_LABEL[source_kind],
                source_root=root,
                source_root_order=source_root_order,
            ),
            diagnostics,
        )
    return None, []


def _context_prompt_kind(filename: str) -> str:
    return "agents_md" if filename.upper() == "AGENTS.MD" else "claude_md"


def _context_descriptor_id(filename: str, source_kind: ResourceSourceKind) -> str:
    source_prefix = "user" if source_kind == "user_global" else "project"
    context_name = "agents" if _context_prompt_kind(filename) == "agents_md" else "claude"
    return f"{source_prefix}.{context_name}"


def _context_read_diagnostic_code(filename: str) -> str:
    return "unreadable_agents_file" if _context_prompt_kind(filename) == "agents_md" else "unreadable_claude_file"


def _nearest_context_descriptor(
    descriptors: list[PromptFragmentDescriptor],
) -> PromptFragmentDescriptor | None:
    for descriptor in reversed(descriptors):
        if descriptor.source_kind == "project_local":
            return descriptor
    return descriptors[-1] if descriptors else None


def _discover_prompts(root: Path) -> tuple[list[PromptFragmentDescriptor], list[ResourceDiagnostic]]:
    return _discover_prompts_from_dir(
        root / "prompts",
        source_kind="project_local",
        source_scope="project",
        source_label=_SOURCE_LABEL["project_local"],
    )


def _discover_skills(root: Path) -> tuple[list[SkillDescriptor], list[ResourceDiagnostic]]:
    return _discover_skills_from_dir(
        root / "skills",
        source_kind="project_local",
        source_scope="project",
        source_label=_SOURCE_LABEL["project_local"],
    )


def _discover_extensions(root: Path) -> tuple[list[ExtensionDescriptor], list[ResourceDiagnostic]]:
    return _discover_extensions_from_dir(
        root / "extensions",
        source_kind="project_local",
        source_scope="project",
        source_label=_SOURCE_LABEL["project_local"],
    )


def _discover_themes(root: Path) -> tuple[list[ThemeDescriptor], list[ResourceDiagnostic]]:
    return _discover_themes_from_dir(
        root / "themes",
        source_kind="project_local",
        source_scope="project",
        source_label=_SOURCE_LABEL["project_local"],
    )


def _discover_prompts_from_dir(
    prompts_dir: Path,
    *,
    source_kind: ResourceSourceKind,
    source_scope: str,
    source_label: str,
    source_root_order: int = 0,
) -> tuple[list[PromptFragmentDescriptor], list[ResourceDiagnostic]]:
    if not prompts_dir.is_dir():
        return [], []

    descriptors: list[PromptFragmentDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    for entry in sorted(prompts_dir.iterdir(), key=lambda path: path.name):
        if entry.is_file() and entry.suffix == ".md":
            text, read_diagnostics = _read_text_file(
                entry,
                diagnostic_code="unreadable_prompt_entry",
                message_prefix="Failed to read prompt entry",
            )
            diagnostics.extend(read_diagnostics)
            if text is None:
                continue
            descriptor, frontmatter_diagnostics = _prompt_descriptor_from_text(
                name=entry.stem,
                source_path=entry,
                text=text,
                canonical_name=entry.name,
                source_kind=source_kind,
                source_scope=source_scope,
                source=source_label,
                source_root=prompts_dir,
                source_root_order=source_root_order,
            )
            diagnostics.extend(frontmatter_diagnostics)
            if descriptor is not None:
                descriptors.append(descriptor)
            continue
        diagnostics.append(
            ResourceDiagnostic(
                code="unsupported_prompt_entry",
                message="Prompt entries must be .md files.",
                source_path=entry,
                resource_type="prompt",
                source_kind=source_kind,
            )
        )
    return descriptors, diagnostics


def _prompt_descriptor_from_text(
    *,
    name: str,
    source_path: Path,
    text: str,
    canonical_name: str,
    source_kind: ResourceSourceKind,
    source_scope: str,
    source: str,
    source_root: Path,
    source_root_order: int = 0,
) -> tuple[PromptFragmentDescriptor | None, list[ResourceDiagnostic]]:
    try:
        parsed = parse_frontmatter(text)
    except FrontmatterParseError as exc:
        return None, [
            _invalid_frontmatter_diagnostic(
                exc,
                source_path=source_path,
                resource_type="prompt",
                source_kind=source_kind,
            )
        ]
    frontmatter = parsed.frontmatter
    body = parsed.body
    description = _frontmatter_string(frontmatter.get("description"))
    argument_hint = _frontmatter_string(frontmatter.get("argument-hint"))
    return (
        PromptFragmentDescriptor(
            name=name,
            source_path=source_path,
            text=text,
            description=description,
            argument_hint=argument_hint,
            metadata={
                "frontmatter": frontmatter,
                "body": body,
            },
            canonical_name=canonical_name,
            source_kind=source_kind,
            source_scope=source_scope,
            source=source,
            source_root=source_root,
            source_root_order=source_root_order,
        ),
        [],
    )


def _discover_skills_from_dir(
    skills_dir: Path,
    *,
    source_kind: ResourceSourceKind,
    source_scope: str,
    source_label: str,
    source_root_order: int = 0,
) -> tuple[list[SkillDescriptor], list[ResourceDiagnostic]]:
    if not skills_dir.is_dir():
        return [], []

    return _discover_skills_recursive(
        skills_dir,
        root_dir=skills_dir,
        ignore_patterns=(),
        source_kind=source_kind,
        source_scope=source_scope,
        source_label=source_label,
        source_root_order=source_root_order,
    )


def _discover_skills_recursive(
    current_dir: Path,
    *,
    root_dir: Path,
    ignore_patterns: tuple[str, ...],
    source_kind: ResourceSourceKind,
    source_scope: str,
    source_label: str,
    source_root_order: int = 0,
) -> tuple[list[SkillDescriptor], list[ResourceDiagnostic]]:
    descriptors: list[SkillDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    active_ignore_patterns = (*ignore_patterns, *_read_skill_ignore_patterns(current_dir, root_dir))
    skill_file = current_dir / "SKILL.md"
    if skill_file.is_file():
        descriptor, skill_diagnostics = _skill_descriptor_from_file(
            skill_file,
            root_dir=root_dir,
            parent_name=current_dir.name,
            source_kind=source_kind,
            source_scope=source_scope,
            source_label=source_label,
            source_root_order=source_root_order,
        )
        diagnostics.extend(skill_diagnostics)
        return ([descriptor] if descriptor is not None else []), diagnostics

    for entry in sorted(current_dir.iterdir(), key=lambda path: path.name):
        if entry.name == "SKILL.md":
            continue
        if entry.is_file():
            if current_dir == root_dir and entry.name not in _IGNORE_FILE_NAMES:
                diagnostics.append(
                    ResourceDiagnostic(
                        code="unsupported_skill_entry",
                        message="Skill entries must be directories.",
                        source_path=entry,
                        resource_type="skill",
                        source_kind=source_kind,
                    )
                )
            continue
        if not entry.is_dir() or _skip_skill_directory(entry):
            continue
        if _is_skill_path_ignored(entry, root_dir=root_dir, patterns=active_ignore_patterns):
            continue
        child_descriptors, child_diagnostics = _discover_skills_recursive(
            entry,
            root_dir=root_dir,
            ignore_patterns=active_ignore_patterns,
            source_kind=source_kind,
            source_scope=source_scope,
            source_label=source_label,
            source_root_order=source_root_order,
        )
        descriptors.extend(child_descriptors)
        diagnostics.extend(child_diagnostics)
    return descriptors, diagnostics


def _skill_descriptor_from_file(
    skill_file: Path,
    *,
    root_dir: Path,
    parent_name: str,
    source_kind: ResourceSourceKind,
    source_scope: str,
    source_label: str,
    source_root_order: int,
) -> tuple[SkillDescriptor | None, list[ResourceDiagnostic]]:
    content, diagnostics = _read_text_file(
        skill_file,
        diagnostic_code="unreadable_skill_entry",
        message_prefix="Failed to read skill entry",
    )
    if content is None:
        return None, diagnostics

    try:
        parsed = parse_frontmatter(content)
    except FrontmatterParseError as exc:
        diagnostics.append(
            _invalid_frontmatter_diagnostic(
                exc,
                source_path=skill_file,
                resource_type="skill",
                source_kind=source_kind,
            )
        )
        return None, diagnostics
    frontmatter = parsed.frontmatter
    body = parsed.body
    skill_name = _frontmatter_string(frontmatter.get("name")) or parent_name
    description = _frontmatter_string(frontmatter.get("description"))
    diagnostics.extend(
        _skill_frontmatter_diagnostics(
            frontmatter=frontmatter,
            skill_name=skill_name,
            parent_name=parent_name,
            source_path=skill_file,
            source_kind=source_kind,
        )
    )
    canonical_name = skill_file.relative_to(root_dir).as_posix()
    return (
        SkillDescriptor(
            name=skill_name,
            source_path=skill_file,
            content=content,
            description=description,
            disable_model_invocation=frontmatter.get("disable-model-invocation") is True,
            metadata={
                "frontmatter": frontmatter,
                "body": body,
            },
            canonical_name=canonical_name,
            source_kind=source_kind,
            source_scope=source_scope,
            source=source_label,
            source_root=root_dir,
            source_root_order=source_root_order,
        ),
        diagnostics,
    )


def _skip_skill_directory(path: Path) -> bool:
    return path.name.startswith(".") or path.name == "node_modules"


def _read_skill_ignore_patterns(current_dir: Path, root_dir: Path) -> tuple[str, ...]:
    patterns: list[str] = []
    relative_prefix = current_dir.relative_to(root_dir).as_posix()
    prefix = "" if relative_prefix == "." else relative_prefix
    for filename in _IGNORE_FILE_NAMES:
        ignore_file = current_dir / filename
        if not ignore_file.is_file():
            continue
        try:
            lines = ignore_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw_line in lines:
            pattern = _normalize_skill_ignore_pattern(raw_line, prefix=prefix)
            if pattern is not None:
                patterns.append(pattern)
    return tuple(patterns)


def _normalize_skill_ignore_pattern(raw_line: str, *, prefix: str) -> str | None:
    line = raw_line.strip()
    if not line or line.startswith("#") or line.startswith("!"):
        return None
    if line.startswith("\\#") or line.startswith("\\!"):
        line = line[1:]
    if line.startswith("/"):
        line = line[1:]
    if prefix and "/" not in line.rstrip("/"):
        line = f"{prefix}/{line}"
    elif prefix:
        line = f"{prefix}/{line}"
    return line


def _is_skill_path_ignored(path: Path, *, root_dir: Path, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return False
    relative_path = path.relative_to(root_dir).as_posix()
    directory_path = f"{relative_path}/"
    for pattern in patterns:
        normalized = pattern.rstrip("/")
        if pattern.endswith("/") and (relative_path == normalized or directory_path.startswith(pattern)):
            return True
        if relative_path == normalized or relative_path.startswith(f"{normalized}/"):
            return True
        if fnmatch(relative_path, normalized) or fnmatch(directory_path, pattern):
            return True
    return False


def _discover_extensions_from_dir(
    extensions_dir: Path,
    *,
    source_kind: ResourceSourceKind,
    source_scope: str,
    source_label: str,
    source_root_order: int = 0,
) -> tuple[list[ExtensionDescriptor], list[ResourceDiagnostic]]:
    if not extensions_dir.is_dir():
        return [], []

    descriptors: list[ExtensionDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    for entry in sorted(extensions_dir.iterdir(), key=lambda path: (0 if path.is_dir() else 1, path.name)):
        if entry.is_file() and entry.suffix == ".py":
            descriptors.append(
                ExtensionDescriptor(
                    name=entry.stem,
                    source_path=entry,
                    entry_path=entry,
                    canonical_name=entry.name,
                    source_kind=source_kind,
                    source_scope=source_scope,
                    source=source_label,
                    source_root=extensions_dir,
                    source_root_order=source_root_order,
                )
            )
            continue
        if entry.is_dir():
            entry_path = _find_extension_entry(entry)
            if entry_path is None:
                diagnostics.append(
                    ResourceDiagnostic(
                        code="missing_extension_entry",
                        message="Extension directories must contain extension.py or __init__.py.",
                        source_path=entry,
                        resource_type="extension",
                        source_kind=source_kind,
                    )
                )
                continue
            descriptors.append(
                ExtensionDescriptor(
                    name=entry.name,
                    source_path=entry,
                    entry_path=entry_path,
                    canonical_name=entry.name,
                    source_kind=source_kind,
                    source_scope=source_scope,
                    source=source_label,
                    source_root=extensions_dir,
                    source_root_order=source_root_order,
                )
            )
            continue
        diagnostics.append(
            ResourceDiagnostic(
                code="unsupported_extension_entry",
                message="Extension entries must be .py files or directories.",
                source_path=entry,
                resource_type="extension",
                source_kind=source_kind,
            )
        )
    return descriptors, diagnostics


def _discover_themes_from_dir(
    themes_dir: Path,
    *,
    source_kind: ResourceSourceKind,
    source_scope: str,
    source_label: str,
    source_root_order: int = 0,
) -> tuple[list[ThemeDescriptor], list[ResourceDiagnostic]]:
    if not themes_dir.is_dir():
        return [], []

    descriptors: list[ThemeDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    for entry in sorted(themes_dir.iterdir(), key=lambda path: path.name):
        if entry.is_file() and not entry.name.endswith(".json"):
            diagnostics.append(
                ResourceDiagnostic(
                    code="unsupported_theme_entry",
                    message="Theme file entries must be .json files.",
                    source_path=entry,
                    resource_type="theme",
                    source_kind=source_kind,
                )
            )
            continue
        if entry.is_file():
            diagnostic = _theme_json_diagnostic(entry, source_kind=source_kind)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
                continue
        descriptors.append(
            ThemeDescriptor(
                name=entry.stem if entry.is_file() else entry.name,
                source_path=entry,
                canonical_name=entry.name,
                source_kind=source_kind,
                source_scope=source_scope,
                source=source_label,
                source_root=themes_dir,
                source_root_order=source_root_order,
            )
        )
    return descriptors, diagnostics


def _theme_json_diagnostic(path: Path, *, source_kind: ResourceSourceKind) -> ResourceDiagnostic | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ResourceDiagnostic(
            code="invalid_theme_json",
            message=f"Theme JSON is invalid: {exc.msg}",
            source_path=path,
            resource_type="theme",
            source_kind=source_kind,
        )
    except Exception as exc:  # noqa: BLE001
        return ResourceDiagnostic(
            code="unreadable_theme_entry",
            message=f"Failed to read theme entry: {exc}",
            source_path=path,
            resource_type="theme",
            source_kind=source_kind,
        )
    if not isinstance(payload, dict):
        return ResourceDiagnostic(
            code="invalid_theme_schema",
            message="Theme JSON must be an object.",
            source_path=path,
            resource_type="theme",
            source_kind=source_kind,
        )
    return None


def _discover_built_in_prompts() -> tuple[list[PromptFragmentDescriptor], list[ResourceDiagnostic]]:
    prompts_root = _built_in_category_root("prompts")
    if prompts_root is None:
        return [], []

    descriptors: list[PromptFragmentDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    for entry in _iter_built_in_entries(prompts_root):
        if entry.is_file() and entry.name.endswith(".md"):
            text, read_diagnostics = _read_text_resource(
                entry,
                relative_path=f"prompts/{entry.name}",
                diagnostic_code="unreadable_prompt_entry",
                message_prefix="Failed to read built-in prompt entry",
            )
            diagnostics.extend(read_diagnostics)
            if text is None:
                continue
            descriptor, frontmatter_diagnostics = _prompt_descriptor_from_text(
                name=entry.name.removesuffix(".md"),
                source_path=_package_resource_path(f"prompts/{entry.name}"),
                text=text,
                canonical_name=entry.name,
                source_kind="built_in",
                source_scope="builtin",
                source="package_resource",
                source_root=_package_source_root_path("prompts"),
            )
            diagnostics.extend(frontmatter_diagnostics)
            if descriptor is not None:
                descriptors.append(descriptor)
            continue
        diagnostics.append(
            ResourceDiagnostic(
                code="unsupported_prompt_entry",
                message="Built-in prompt entries must be .md files.",
                source_path=_package_resource_path(f"prompts/{entry.name}"),
                resource_type="prompt",
                source_kind="built_in",
            )
        )
    return descriptors, diagnostics


def _discover_built_in_skills() -> tuple[list[SkillDescriptor], list[ResourceDiagnostic]]:
    skills_root = _built_in_category_root("skills")
    if skills_root is None:
        return [], []

    descriptors: list[SkillDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    for entry in _iter_built_in_entries(skills_root):
        if not entry.is_dir():
            diagnostics.append(
                ResourceDiagnostic(
                    code="unsupported_skill_entry",
                    message="Built-in skill entries must be directories.",
                    source_path=_package_resource_path(f"skills/{entry.name}"),
                    resource_type="skill",
                    source_kind="built_in",
                )
            )
            continue

        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            diagnostics.append(
                ResourceDiagnostic(
                    code="missing_skill_entry",
                    message="Built-in skill directories must contain SKILL.md.",
                    source_path=_package_resource_path(f"skills/{entry.name}"),
                    resource_type="skill",
                    source_kind="built_in",
                )
            )
            continue

        content, read_diagnostics = _read_text_resource(
            skill_file,
            relative_path=f"skills/{entry.name}/SKILL.md",
            diagnostic_code="unreadable_skill_entry",
            message_prefix="Failed to read built-in skill entry",
        )
        diagnostics.extend(read_diagnostics)
        if content is None:
            continue

        try:
            parsed = parse_frontmatter(content)
        except FrontmatterParseError as exc:
            diagnostics.append(
                _invalid_frontmatter_diagnostic(
                    exc,
                    source_path=_package_resource_path(f"skills/{entry.name}/SKILL.md"),
                    resource_type="skill",
                    source_kind="built_in",
                )
            )
            continue
        frontmatter = parsed.frontmatter
        body = parsed.body
        skill_name = _frontmatter_string(frontmatter.get("name")) or entry.name
        description = _frontmatter_string(frontmatter.get("description"))
        diagnostics.extend(
            _skill_frontmatter_diagnostics(
                frontmatter=frontmatter,
                skill_name=skill_name,
                parent_name=entry.name,
                source_path=_package_resource_path(f"skills/{entry.name}/SKILL.md"),
                source_kind="built_in",
            )
        )
        descriptors.append(
            SkillDescriptor(
                name=skill_name,
                source_path=_package_resource_path(f"skills/{entry.name}/SKILL.md"),
                content=content,
                description=description,
                disable_model_invocation=frontmatter.get("disable-model-invocation") is True,
                metadata={
                    "frontmatter": frontmatter,
                    "body": body,
                },
                canonical_name=f"{entry.name}/SKILL.md",
                source_kind="built_in",
                source_scope="builtin",
                source="package_resource",
                source_root=_package_source_root_path("skills"),
            )
        )
    return descriptors, diagnostics


def _discover_built_in_extensions() -> tuple[list[ExtensionDescriptor], list[ResourceDiagnostic]]:
    extensions_root = _built_in_category_root("extensions")
    if extensions_root is None:
        return [], []

    descriptors: list[ExtensionDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    for entry in _iter_built_in_entries(extensions_root):
        if entry.is_file() and entry.name.endswith(".py"):
            entry_path = _package_resource_path(f"extensions/{entry.name}")
            descriptors.append(
                ExtensionDescriptor(
                    name=entry.name.removesuffix(".py"),
                    source_path=entry_path,
                    entry_path=entry_path,
                    canonical_name=entry.name,
                    source_kind="built_in",
                    source_scope="builtin",
                    source="package_resource",
                    source_root=_package_source_root_path("extensions"),
                )
            )
            continue
        if entry.is_dir():
            entry_name = _find_extension_entry_name(entry)
            if entry_name is None:
                diagnostics.append(
                    ResourceDiagnostic(
                        code="missing_extension_entry",
                        message="Built-in extension directories must contain extension.py or __init__.py.",
                        source_path=_package_resource_path(f"extensions/{entry.name}"),
                        resource_type="extension",
                        source_kind="built_in",
                    )
                )
                continue
            descriptors.append(
                ExtensionDescriptor(
                    name=entry.name,
                    source_path=_package_resource_path(f"extensions/{entry.name}"),
                    entry_path=_package_resource_path(f"extensions/{entry.name}/{entry_name}"),
                    canonical_name=entry.name,
                    source_kind="built_in",
                    source_scope="builtin",
                    source="package_resource",
                    source_root=_package_source_root_path("extensions"),
                )
            )
            continue
        diagnostics.append(
            ResourceDiagnostic(
                code="unsupported_extension_entry",
                message="Built-in extension entries must be .py files or directories.",
                source_path=_package_resource_path(f"extensions/{entry.name}"),
                resource_type="extension",
                source_kind="built_in",
            )
        )
    return descriptors, diagnostics


def _discover_built_in_themes() -> tuple[list[ThemeDescriptor], list[ResourceDiagnostic]]:
    themes_root = _built_in_category_root("themes")
    if themes_root is None:
        return [], []

    descriptors = [
        ThemeDescriptor(
            name=entry.name.removesuffix(".json") if entry.is_file() else entry.name,
            source_path=_package_resource_path(f"themes/{entry.name}"),
            canonical_name=entry.name,
            source_kind="built_in",
            source_scope="builtin",
            source="package_resource",
            source_root=_package_source_root_path("themes"),
        )
        for entry in _iter_built_in_entries(themes_root)
    ]
    return descriptors, []


def _iter_built_in_entries(root: Traversable) -> list[Traversable]:
    entries = []
    for entry in root.iterdir():
        if entry.name in {"__init__.py", "__pycache__"}:
            continue
        entries.append(entry)
    return sorted(entries, key=lambda entry: entry.name)


def _built_in_category_root(category: str) -> Traversable | None:
    try:
        root = resources.files(BUILT_IN_RESOURCE_PACKAGE)
    except ModuleNotFoundError:
        return None
    category_root = root / category
    if not category_root.is_dir():
        return None
    return category_root


def _find_extension_entry(entry: Path) -> Path | None:
    for filename in ("extension.py", "__init__.py"):
        candidate = entry / filename
        if candidate.is_file():
            return candidate
    return None


def _find_extension_entry_name(entry: Traversable) -> str | None:
    for filename in ("extension.py", "__init__.py"):
        candidate = entry / filename
        if candidate.is_file():
            return filename
    return None


def _read_text_file(
    path: Path,
    *,
    diagnostic_code: str,
    message_prefix: str,
) -> tuple[str | None, list[ResourceDiagnostic]]:
    try:
        return path.read_text(encoding="utf-8").strip(), []
    except OSError as exc:
        return (
            None,
            [
                ResourceDiagnostic(
                    code=diagnostic_code,
                    message=f"{message_prefix}: {exc}",
                    source_path=path,
                )
            ],
        )


def _invalid_frontmatter_diagnostic(
    error: FrontmatterParseError,
    *,
    source_path: Path,
    resource_type: str,
    source_kind: ResourceSourceKind,
) -> ResourceDiagnostic:
    return ResourceDiagnostic(
        code=f"invalid_{resource_type}_frontmatter",
        message=str(error),
        source_path=source_path,
        resource_type=resource_type,
        source_kind=source_kind,
    )


def _skill_frontmatter_diagnostics(
    *,
    frontmatter: dict[str, object],
    skill_name: str,
    parent_name: str,
    source_path: Path,
    source_kind: ResourceSourceKind,
) -> list[ResourceDiagnostic]:
    if not frontmatter:
        return []
    diagnostics: list[ResourceDiagnostic] = []
    description = _frontmatter_string(frontmatter.get("description"))
    if description is None:
        diagnostics.append(
            _skill_validation_diagnostic(
                code="invalid_skill_description",
                message="Skill frontmatter description is required.",
                source_path=source_path,
                source_kind=source_kind,
                field="description",
            )
        )
    elif len(description) > _MAX_SKILL_DESCRIPTION_LENGTH:
        diagnostics.append(
            _skill_validation_diagnostic(
                code="invalid_skill_description",
                message=f"Skill frontmatter description exceeds {_MAX_SKILL_DESCRIPTION_LENGTH} characters.",
                source_path=source_path,
                source_kind=source_kind,
                field="description",
            )
        )
    if skill_name != parent_name:
        diagnostics.append(
            _skill_validation_diagnostic(
                code="invalid_skill_name",
                message=f'Skill frontmatter name "{skill_name}" does not match parent directory "{parent_name}".',
                source_path=source_path,
                source_kind=source_kind,
                field="name",
            )
        )
    if len(skill_name) > _MAX_SKILL_NAME_LENGTH:
        diagnostics.append(
            _skill_validation_diagnostic(
                code="invalid_skill_name",
                message=f"Skill frontmatter name exceeds {_MAX_SKILL_NAME_LENGTH} characters.",
                source_path=source_path,
                source_kind=source_kind,
                field="name",
            )
        )
    if not _is_valid_skill_name(skill_name):
        diagnostics.append(
            _skill_validation_diagnostic(
                code="invalid_skill_name",
                message="Skill frontmatter name must contain lowercase letters, numbers, and hyphens only.",
                source_path=source_path,
                source_kind=source_kind,
                field="name",
            )
        )
    return diagnostics


def _skill_validation_diagnostic(
    *,
    code: str,
    message: str,
    source_path: Path,
    source_kind: ResourceSourceKind,
    field: str,
) -> ResourceDiagnostic:
    return ResourceDiagnostic(
        code=code,
        message=message,
        source_path=source_path,
        resource_type="skill",
        source_kind=source_kind,
        metadata={"field": field},
    )


def _is_valid_skill_name(name: str) -> bool:
    if not name or name.startswith("-") or name.endswith("-") or "--" in name:
        return False
    return all(char.islower() or char.isdigit() or char == "-" for char in name)


def _frontmatter_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _read_text_resource(
    resource: Traversable,
    *,
    relative_path: str,
    diagnostic_code: str,
    message_prefix: str,
) -> tuple[str | None, list[ResourceDiagnostic]]:
    logical_path = _package_resource_path(relative_path)
    try:
        return resource.read_text(encoding="utf-8").strip(), []
    except OSError as exc:
        return (
            None,
            [
                ResourceDiagnostic(
                    code=diagnostic_code,
                    message=f"{message_prefix}: {exc}",
                    source_path=logical_path,
                    source_kind="built_in",
                )
            ],
        )


def _package_resource_path(relative_path: str) -> Path:
    return Path(BUILT_IN_RESOURCE_PACKAGE.replace(".", "/")) / relative_path


def _package_source_root_path(category: str) -> Path:
    return Path(BUILT_IN_RESOURCE_PACKAGE.replace(".", "/")) / category


def _normalize_package_roots(package_roots: list[str | Path] | tuple[str | Path, ...] | None) -> tuple[Path, ...]:
    if not package_roots:
        return ()
    return tuple(Path(root).expanduser().resolve() for root in package_roots)


def _normalize_package_source_filters(
    package_source_filters: dict[str | Path, PackageSourceConfig] | None,
) -> dict[Path, PackageSourceConfig]:
    if not package_source_filters:
        return {}
    return {Path(root).expanduser().resolve(): config for root, config in package_source_filters.items()}


def _filter_package_descriptors(
    descriptors: list[DescriptorT],
    *,
    root: Path,
    patterns: tuple[str, ...] | None,
) -> list[DescriptorT]:
    if patterns is None:
        return descriptors
    if not patterns:
        return []
    includes = [pattern for pattern in patterns if not _is_override_pattern(pattern)]
    excludes = [pattern[1:] for pattern in patterns if pattern.startswith("!")]
    force_includes = [pattern[1:] for pattern in patterns if pattern.startswith("+")]
    force_excludes = [pattern[1:] for pattern in patterns if pattern.startswith("-")]
    filtered: list[DescriptorT] = []
    for descriptor in descriptors:
        enabled = True if not includes else _descriptor_matches_patterns(descriptor, root=root, patterns=tuple(includes))
        if excludes and _descriptor_matches_patterns(descriptor, root=root, patterns=tuple(excludes)):
            enabled = False
        if force_includes and _descriptor_matches_patterns(descriptor, root=root, patterns=tuple(force_includes), exact=True):
            enabled = True
        if force_excludes and _descriptor_matches_patterns(descriptor, root=root, patterns=tuple(force_excludes), exact=True):
            enabled = False
        if enabled:
            filtered.append(descriptor)
    return filtered


def _is_override_pattern(pattern: str) -> bool:
    return pattern.startswith(("!", "+", "-"))


def _descriptor_matches_patterns(
    descriptor: DescriptorT,
    *,
    root: Path,
    patterns: tuple[str, ...],
    exact: bool = False,
) -> bool:
    values = _descriptor_match_values(descriptor, root=root)
    if exact:
        return any(value == pattern.lstrip("./") for pattern in patterns for value in values)
    return any(fnmatch(value, pattern) for pattern in patterns for value in values)


def _descriptor_match_values(descriptor: DescriptorT, *, root: Path) -> tuple[str, ...]:
    values = {
        descriptor.name,
        descriptor.id or "",
        descriptor.canonical_name or "",
        descriptor.source_path.name,
        descriptor.source_path.parent.name,
    }
    try:
        relative_path = descriptor.source_path.resolve().relative_to(root).as_posix()
    except ValueError:
        relative_path = descriptor.source_path.as_posix()
    values.add(relative_path)
    return tuple(value for value in values if value)


def _package_root_diagnostic(code: str, message: str, root: Path) -> ResourceDiagnostic:
    return ResourceDiagnostic(
        code=code,
        message=message,
        source_path=root,
        resource_type="package",
        source_kind="external_package",
        metadata={"package_root": str(root)},
    )


def _count_package_descriptors(descriptors: tuple[DescriptorT, ...], root: Path) -> int:
    return sum(1 for descriptor in descriptors if _path_belongs_to_root(descriptor.source_path, root))


def _count_package_diagnostics(diagnostics: tuple[ResourceDiagnostic, ...], root: Path) -> int:
    return sum(1 for diagnostic in diagnostics if _diagnostic_belongs_to_root(diagnostic, root))


def _diagnostic_belongs_to_root(diagnostic: ResourceDiagnostic, root: Path) -> bool:
    package_root = diagnostic.metadata.get("package_root")
    if package_root == str(root):
        return True
    if diagnostic.source_path is None:
        return False
    return _path_belongs_to_root(diagnostic.source_path, root)


def _path_belongs_to_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def _source_kinds_for(
    package_roots: tuple[Path, ...],
    user_resource_roots: tuple[Path, ...] = (),
    *,
    has_temporary: bool = False,
) -> tuple[ResourceSourceKind, ...]:
    kinds: list[ResourceSourceKind] = []
    if has_temporary:
        kinds.append("temporary")
    kinds.append("built_in")
    if user_resource_roots:
        kinds.append("user_global")
    if package_roots:
        kinds.append("external_package")
    kinds.append("project_local")
    return tuple(kinds)


def _source_precedence_rank(source_kind: ResourceSourceKind) -> int:
    return _SOURCE_PRIORITY[source_kind]


def _normalize_user_resource_roots(user_resource_roots: list[str | Path] | tuple[str | Path, ...] | None) -> tuple[Path, ...]:
    if not user_resource_roots:
        return ()
    return tuple(Path(root).expanduser().resolve() for root in user_resource_roots)


def _normalize_runtime_paths(paths: list[str | Path] | tuple[str | Path, ...] | None) -> tuple[Path, ...]:
    if not paths:
        return ()
    return tuple(Path(path).expanduser() for path in paths)


def _resolve_runtime_path(path: Path, cwd: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (cwd / expanded).resolve()


def _resolve_prompt_input(source: str | None, *, cwd: Path) -> str | None:
    if not source:
        return None
    candidate = Path(source).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    if not candidate.exists():
        return source
    if not candidate.is_file():
        return source
    try:
        return candidate.read_text(encoding="utf-8")
    except OSError:
        return source


def _resolve_candidates(
    candidates: list[DescriptorT],
    *,
    resource_type: str,
) -> tuple[list[DescriptorT], list[ResourceDiagnostic], list[ResourceMergeDecision]]:
    grouped: dict[str, list[DescriptorT]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.id or candidate.name, []).append(candidate)

    active: list[DescriptorT] = []
    diagnostics: list[ResourceDiagnostic] = []
    decisions: list[ResourceMergeDecision] = []
    for logical_id, group_members in grouped.items():
        group = sorted(group_members, key=_candidate_sort_key)
        enabled_candidates = [candidate for candidate in group if candidate.enabled]
        winner = min(enabled_candidates, key=_winner_sort_key) if enabled_candidates else None
        if winner is not None:
            active.append(winner)

        for candidate in group:
            if candidate.enabled:
                continue
            diagnostics.append(
                ResourceDiagnostic(
                    code="resource_disabled",
                    message=f"{resource_type} resource '{logical_id}' is disabled.",
                    source_path=candidate.source_path,
                    resource_id=candidate.id,
                    resource_type=resource_type,
                    source_kind=candidate.source_kind,
                )
            )

        if len(group) > 1:
            candidate_ids = tuple(candidate.id or candidate.name for candidate in group)
            candidate_source_kinds = tuple(candidate.source_kind for candidate in group)
            if winner is None:
                message = f"{resource_type} resource '{logical_id}' has no enabled candidates."
            else:
                message = (
                    f"{resource_type} resource '{logical_id}' selected {winner.source_kind} "
                    f"candidate '{winner.id}' over lower-priority or later-tiebreak candidates."
                )
            diagnostics.append(
                ResourceDiagnostic(
                    code="resource_collision",
                    message=message,
                    source_path=winner.source_path if winner is not None else group[0].source_path,
                    resource_id=logical_id,
                    resource_type=resource_type,
                    source_kind=winner.source_kind if winner is not None else group[0].source_kind,
                    metadata={
                        "winner_id": winner.id if winner is not None else None,
                        "candidate_ids": candidate_ids,
                        "candidate_source_kinds": candidate_source_kinds,
                        **_collision_path_metadata(winner=winner, candidates=group),
                    },
                )
            )
            decisions.append(
                ResourceMergeDecision(
                    resource_type=resource_type,
                    logical_id=logical_id,
                    winner_id=winner.id if winner is not None else None,
                    winner_source_kind=winner.source_kind if winner is not None else None,
                    candidate_ids=candidate_ids,
                    candidate_source_kinds=candidate_source_kinds,
                    reason="precedence_and_tiebreak",
                )
            )
        elif winner is not None:
            decisions.append(
                ResourceMergeDecision(
                    resource_type=resource_type,
                    logical_id=logical_id,
                    winner_id=winner.id,
                    winner_source_kind=winner.source_kind,
                    candidate_ids=(winner.id,),
                    candidate_source_kinds=(winner.source_kind,),
                    reason="single_candidate",
                )
            )

    return active, diagnostics, decisions


def _resolve_strict_named_candidates(
    candidates: list[DescriptorT],
    *,
    resource_type: str,
) -> tuple[list[DescriptorT], list[ResourceDiagnostic], list[ResourceMergeDecision]]:
    grouped: dict[str, list[DescriptorT]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.id or candidate.name, []).append(candidate)

    active: list[DescriptorT] = []
    diagnostics: list[ResourceDiagnostic] = []
    decisions: list[ResourceMergeDecision] = []
    for logical_id, group_members in grouped.items():
        group = sorted(group_members, key=_candidate_sort_key)
        enabled_candidates = [candidate for candidate in group if candidate.enabled]

        for candidate in group:
            if candidate.enabled:
                continue
            diagnostics.append(
                ResourceDiagnostic(
                    code="resource_disabled",
                    message=f"{resource_type} resource '{logical_id}' is disabled.",
                    source_path=candidate.source_path,
                    resource_id=candidate.id,
                    resource_type=resource_type,
                    source_kind=candidate.source_kind,
                )
            )

        if not enabled_candidates:
            if len(group) > 1:
                candidate_ids = tuple(candidate.id or candidate.name for candidate in group)
                candidate_source_kinds = tuple(candidate.source_kind for candidate in group)
                diagnostics.append(
                    ResourceDiagnostic(
                        code="resource_collision",
                        message=f"{resource_type} resource '{logical_id}' has no enabled candidates.",
                        source_path=group[0].source_path,
                        resource_id=logical_id,
                        resource_type=resource_type,
                        source_kind=group[0].source_kind,
                        metadata={
                            "winner_id": None,
                            "candidate_ids": candidate_ids,
                            "candidate_source_kinds": candidate_source_kinds,
                            **_collision_path_metadata(winner=None, candidates=group),
                        },
                    )
                )
                decisions.append(
                    ResourceMergeDecision(
                        resource_type=resource_type,
                        logical_id=logical_id,
                        winner_id=None,
                        winner_source_kind=None,
                        candidate_ids=candidate_ids,
                        candidate_source_kinds=candidate_source_kinds,
                        reason="no_enabled_candidates",
                    )
                )
            continue

        winner = enabled_candidates[0]
        candidate_ids = tuple(candidate.id or candidate.name for candidate in group)
        candidate_source_kinds = tuple(candidate.source_kind for candidate in group)
        top_rank = _source_precedence_rank(winner.source_kind)
        top_tier = [candidate for candidate in enabled_candidates if _source_precedence_rank(candidate.source_kind) == top_rank]

        if len(top_tier) > 1:
            diagnostics.append(
                ResourceDiagnostic(
                    code="resource_collision",
                    message=f"{resource_type} resource '{logical_id}' has conflicting same-precedence candidates.",
                    source_path=top_tier[0].source_path,
                    resource_id=logical_id,
                    resource_type=resource_type,
                    source_kind=top_tier[0].source_kind,
                    metadata={
                        "winner_id": None,
                        "candidate_ids": candidate_ids,
                        "candidate_source_kinds": candidate_source_kinds,
                        **_collision_path_metadata(winner=None, candidates=group),
                    },
                )
            )
            decisions.append(
                ResourceMergeDecision(
                    resource_type=resource_type,
                    logical_id=logical_id,
                    winner_id=None,
                    winner_source_kind=None,
                    candidate_ids=candidate_ids,
                    candidate_source_kinds=candidate_source_kinds,
                    reason="same_precedence_conflict",
                )
            )
            continue

        active.append(winner)
        if len(group) > 1:
            diagnostics.append(
                ResourceDiagnostic(
                    code="resource_collision",
                    message=(
                        f"{resource_type} resource '{logical_id}' selected {winner.source_kind} "
                        f"candidate '{winner.id}' over lower-precedence candidates."
                    ),
                    source_path=winner.source_path,
                    resource_id=logical_id,
                    resource_type=resource_type,
                    source_kind=winner.source_kind,
                    metadata={
                        "winner_id": winner.id,
                        "candidate_ids": candidate_ids,
                        "candidate_source_kinds": candidate_source_kinds,
                        **_collision_path_metadata(winner=winner, candidates=group),
                    },
                )
            )
            decisions.append(
                ResourceMergeDecision(
                    resource_type=resource_type,
                    logical_id=logical_id,
                    winner_id=winner.id,
                    winner_source_kind=winner.source_kind,
                    candidate_ids=candidate_ids,
                    candidate_source_kinds=candidate_source_kinds,
                    reason="source_precedence",
                )
            )
        else:
            decisions.append(
                ResourceMergeDecision(
                    resource_type=resource_type,
                    logical_id=logical_id,
                    winner_id=winner.id,
                    winner_source_kind=winner.source_kind,
                    candidate_ids=(winner.id,),
                    candidate_source_kinds=(winner.source_kind,),
                    reason="single_candidate",
                )
            )

    return active, diagnostics, decisions


def _collision_path_metadata(
    *,
    winner: DescriptorT | None,
    candidates: list[DescriptorT],
) -> dict[str, object]:
    winner_path = str(winner.source_path) if winner is not None else None
    candidate_paths = tuple(str(candidate.source_path) for candidate in candidates)
    loser_paths = tuple(str(candidate.source_path) for candidate in candidates if candidate is not winner)
    return {
        "winner_path": winner_path,
        "candidate_paths": candidate_paths,
        "loser_paths": loser_paths,
    }


def _resolve_extension_candidates(
    candidates: list[ExtensionDescriptor],
    *,
    resource_type: str,
) -> tuple[list[ExtensionDescriptor], list[ResourceDiagnostic], list[ResourceMergeDecision]]:
    ordered = sorted(candidates, key=_candidate_sort_key)
    active: list[ExtensionDescriptor] = []
    diagnostics: list[ResourceDiagnostic] = []
    decisions: list[ResourceMergeDecision] = []

    grouped: dict[str, list[ExtensionDescriptor]] = {}
    for candidate in ordered:
        grouped.setdefault(candidate.id or candidate.name, []).append(candidate)
        if candidate.enabled:
            active.append(candidate)
            continue
        diagnostics.append(
            ResourceDiagnostic(
                code="resource_disabled",
                message=f"{resource_type} resource '{candidate.id or candidate.name}' is disabled.",
                source_path=candidate.source_path,
                resource_id=candidate.id,
                resource_type=resource_type,
                source_kind=candidate.source_kind,
            )
        )

    for logical_id, group in grouped.items():
        enabled_group = [candidate for candidate in group if candidate.enabled]
        if not enabled_group:
            decisions.append(
                ResourceMergeDecision(
                    resource_type=resource_type,
                    logical_id=logical_id,
                    winner_id=None,
                    winner_source_kind=None,
                    candidate_ids=tuple(candidate.id or candidate.name for candidate in group),
                    candidate_source_kinds=tuple(candidate.source_kind for candidate in group),
                    reason="no_enabled_candidates",
                )
            )
            continue
        decisions.append(
            ResourceMergeDecision(
                resource_type=resource_type,
                logical_id=logical_id,
                winner_id=enabled_group[0].id,
                winner_source_kind=enabled_group[0].source_kind,
                candidate_ids=tuple(candidate.id or candidate.name for candidate in group),
                candidate_source_kinds=tuple(candidate.source_kind for candidate in group),
                reason="all_enabled_candidates_active" if len(enabled_group) > 1 else "single_candidate",
            )
        )

    return active, diagnostics, decisions


def _winner_sort_key(descriptor: DescriptorT) -> tuple[int, int, str, str]:
    return (
        _source_precedence_rank(descriptor.source_kind),
        descriptor.source_root_order,
        descriptor.canonical_name or descriptor.name,
        descriptor.source_path.as_posix(),
    )


def _candidate_sort_key(descriptor: DescriptorT) -> tuple[int, int, str, str]:
    return (
        _source_precedence_rank(descriptor.source_kind),
        descriptor.source_root_order,
        descriptor.canonical_name or descriptor.name,
        descriptor.source_path.as_posix(),
    )
