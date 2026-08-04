"""User, project, package, and temporary resource discovery coordination."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from loushang.harness.diagnostics.types import DiagnosticDraft
from loushang.harness.resources._loader_descriptor_parsing import (
    _prompt_descriptor_from_text,
)
from loushang.harness.resources._loader_discovery_filesystem import (
    _discover_extensions_from_dir,
    _discover_prompts_from_dir,
    _discover_skills_from_dir,
    _discover_themes_from_dir,
    _find_extension_entry,
    _read_text_file,
    _skill_descriptor_from_file,
    _theme_json_diagnostic,
)
from loushang.harness.resources._loader_package_policy import (
    _filter_package_descriptors,
    _package_root_diagnostic,
)
from loushang.harness.resources._loader_types import _SOURCE_LABEL, _SourceDiscovery
from loushang.harness.resources.diagnostics import resource_diagnostic
from loushang.harness.resources.types import (
    ExtensionDescriptor,
    PromptFragmentDescriptor,
    SkillDescriptor,
    ThemeDescriptor,
)

if TYPE_CHECKING:
    from loushang.harness.resources.packages.source import PackageSourceConfig


def _discover_user_global_resources(
    user_resource_roots: tuple[Path, ...],
    *,
    explicit_roots: set[Path] | None = None,
) -> _SourceDiscovery:
    prompts: list[PromptFragmentDescriptor] = []
    skills: list[SkillDescriptor] = []
    extensions: list[ExtensionDescriptor] = []
    themes: list[ThemeDescriptor] = []
    diagnostics: list[DiagnosticDraft] = []
    explicit = explicit_roots or set()

    for index, root in enumerate(user_resource_roots):
        if not root.exists():
            if root in explicit:
                diagnostics.append(
                    resource_diagnostic(
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
                    resource_diagnostic(
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
        diagnostics.extend(
            [
                *prompt_diagnostics,
                *skill_diagnostics,
                *extension_diagnostics,
                *theme_diagnostics,
            ]
        )

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
    diagnostics: list[DiagnosticDraft] = []

    for index, root in enumerate(package_roots):
        if not root.exists():
            diagnostics.append(
                _package_root_diagnostic(
                    "missing_package_root", "Package root does not exist.", root
                )
            )
            continue
        if not root.is_dir():
            diagnostics.append(
                _package_root_diagnostic(
                    "invalid_package_root", "Package root must be a directory.", root
                )
            )
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
            package_prompts = _filter_package_descriptors(
                package_prompts, root=root, patterns=package_filter.prompts
            )
            package_skills = _filter_package_descriptors(
                package_skills, root=root, patterns=package_filter.skills
            )
            package_extensions = _filter_package_descriptors(
                package_extensions, root=root, patterns=package_filter.extensions
            )
            package_themes = _filter_package_descriptors(
                package_themes, root=root, patterns=package_filter.themes
            )
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
        if (
            not package_prompts
            and not package_skills
            and not package_extensions
            and not package_themes
            and not package_diagnostics
        ):
            diagnostics.append(
                _package_root_diagnostic(
                    "empty_package_root",
                    "Package root contains no loadable resources.",
                    root,
                )
            )

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
    diagnostics: list[DiagnosticDraft] = []

    for index, raw_path in enumerate(prompt_paths):
        loaded_prompts, loaded_diagnostics = _discover_temporary_prompts_from_path(
            _resolve_runtime_path(raw_path, cwd), index
        )
        prompts.extend(loaded_prompts)
        diagnostics.extend(loaded_diagnostics)
    for index, raw_path in enumerate(skill_paths):
        loaded_skills, loaded_diagnostics = _discover_temporary_skills_from_path(
            _resolve_runtime_path(raw_path, cwd), index
        )
        skills.extend(loaded_skills)
        diagnostics.extend(loaded_diagnostics)
    for index, raw_path in enumerate(extension_paths):
        loaded_extensions, loaded_diagnostics = (
            _discover_temporary_extensions_from_path(
                _resolve_runtime_path(raw_path, cwd), index
            )
        )
        extensions.extend(loaded_extensions)
        diagnostics.extend(loaded_diagnostics)
    for index, raw_path in enumerate(theme_paths):
        loaded_themes, loaded_diagnostics = _discover_temporary_themes_from_path(
            _resolve_runtime_path(raw_path, cwd), index
        )
        themes.extend(loaded_themes)
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
) -> tuple[list[PromptFragmentDescriptor], list[DiagnosticDraft]]:
    if not path.exists():
        return [], [_temporary_missing_path_diagnostic(path, resource_type="prompt")]
    if path.is_file():
        if path.suffix != ".md":
            return [], [
                _temporary_unsupported_path_diagnostic(
                    path,
                    resource_type="prompt",
                    message="Prompt template paths must be .md files or directories.",
                )
            ]
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
) -> tuple[list[SkillDescriptor], list[DiagnosticDraft]]:
    if not path.exists():
        return [], [_temporary_missing_path_diagnostic(path, resource_type="skill")]
    if path.is_file():
        if path.name != "SKILL.md":
            return [], [
                _temporary_unsupported_path_diagnostic(
                    path,
                    resource_type="skill",
                    message="Skill paths must be SKILL.md files or directories.",
                )
            ]
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
) -> tuple[list[ExtensionDescriptor], list[DiagnosticDraft]]:
    if not path.exists():
        return [], [_temporary_missing_path_diagnostic(path, resource_type="extension")]
    if path.is_file():
        if path.suffix != ".py":
            return [], [
                _temporary_unsupported_path_diagnostic(
                    path,
                    resource_type="extension",
                    message="Extension paths must be .py files or directories.",
                )
            ]
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
) -> tuple[list[ThemeDescriptor], list[DiagnosticDraft]]:
    if not path.exists():
        return [], [_temporary_missing_path_diagnostic(path, resource_type="theme")]
    if path.is_file():
        if path.suffix != ".json":
            return [], [
                _temporary_unsupported_path_diagnostic(
                    path,
                    resource_type="theme",
                    message="Theme paths must be .json files or directories.",
                )
            ]
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


def _temporary_missing_path_diagnostic(
    path: Path, *, resource_type: str
) -> DiagnosticDraft:
    return resource_diagnostic(
        code=f"missing_{resource_type}_path",
        message=f"{resource_type.title()} path does not exist: {path}",
        source_path=path,
        resource_type=resource_type,
        source_kind="temporary",
        metadata={"path": str(path)},
    )


def _temporary_unsupported_path_diagnostic(
    path: Path, *, resource_type: str, message: str
) -> DiagnosticDraft:
    return resource_diagnostic(
        code=f"unsupported_{resource_type}_path",
        message=message,
        source_path=path,
        resource_type=resource_type,
        source_kind="temporary",
        metadata={"path": str(path)},
    )


def _discover_prompts(
    root: Path,
) -> tuple[list[PromptFragmentDescriptor], list[DiagnosticDraft]]:
    return _discover_prompts_from_dir(
        root / "prompts",
        source_kind="project_local",
        source_scope="project",
        source_label=_SOURCE_LABEL["project_local"],
    )


def _discover_skills(
    root: Path,
) -> tuple[list[SkillDescriptor], list[DiagnosticDraft]]:
    return _discover_skills_from_dir(
        root / "skills",
        source_kind="project_local",
        source_scope="project",
        source_label=_SOURCE_LABEL["project_local"],
    )


def _discover_extensions(
    root: Path,
) -> tuple[list[ExtensionDescriptor], list[DiagnosticDraft]]:
    return _discover_extensions_from_dir(
        root / "extensions",
        source_kind="project_local",
        source_scope="project",
        source_label=_SOURCE_LABEL["project_local"],
    )


def _discover_themes(
    root: Path,
) -> tuple[list[ThemeDescriptor], list[DiagnosticDraft]]:
    return _discover_themes_from_dir(
        root / "themes",
        source_kind="project_local",
        source_scope="project",
        source_label=_SOURCE_LABEL["project_local"],
    )


def _normalize_user_resource_roots(
    user_resource_roots: Sequence[str | Path] | None,
) -> tuple[Path, ...]:
    if not user_resource_roots:
        return ()
    return tuple(Path(root).expanduser().resolve() for root in user_resource_roots)


def _normalize_runtime_paths(
    paths: list[str | Path] | tuple[str | Path, ...] | None,
) -> tuple[Path, ...]:
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
