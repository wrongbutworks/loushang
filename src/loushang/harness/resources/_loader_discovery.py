"""Filesystem, package, and built-in resource discovery stages."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING

from loushang.harness.diagnostics.types import DiagnosticDraft
from loushang.harness.resources._loader_descriptor_parsing import (
    _prompt_descriptor_from_text,
    _skill_descriptor_from_text,
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


def _discover_built_in_resources(
    resource_packages: tuple[str, ...],
) -> _SourceDiscovery:
    prompts: list[PromptFragmentDescriptor] = []
    skills: list[SkillDescriptor] = []
    extensions: list[ExtensionDescriptor] = []
    themes: list[ThemeDescriptor] = []
    diagnostics: list[DiagnosticDraft] = []
    for index, resource_package in enumerate(resource_packages):
        package_prompts, prompt_diagnostics = _discover_built_in_prompts(
            resource_package,
            source_root_order=index,
        )
        package_skills, skill_diagnostics = _discover_built_in_skills(
            resource_package,
            source_root_order=index,
        )
        package_extensions, extension_diagnostics = _discover_built_in_extensions(
            resource_package,
            source_root_order=index,
        )
        package_themes, theme_diagnostics = _discover_built_in_themes(
            resource_package,
            source_root_order=index,
        )
        prompts.extend(package_prompts)
        skills.extend(package_skills)
        extensions.extend(package_extensions)
        themes.extend(package_themes)
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


def _discover_built_in_prompts(
    resource_package: str,
    *,
    source_root_order: int,
) -> tuple[list[PromptFragmentDescriptor], list[DiagnosticDraft]]:
    prompts_root = _built_in_category_root(resource_package, "prompts")
    if prompts_root is None:
        return [], []

    descriptors: list[PromptFragmentDescriptor] = []
    diagnostics: list[DiagnosticDraft] = []
    for entry in _iter_built_in_entries(prompts_root):
        if entry.is_file() and entry.name.endswith(".md"):
            text, read_diagnostics = _read_text_resource(
                entry,
                resource_package=resource_package,
                relative_path=f"prompts/{entry.name}",
                diagnostic_code="unreadable_prompt_entry",
                message_prefix="Failed to read built-in prompt entry",
            )
            diagnostics.extend(read_diagnostics)
            if text is None:
                continue
            descriptor, frontmatter_diagnostics = _prompt_descriptor_from_text(
                name=entry.name.removesuffix(".md"),
                source_path=_package_resource_path(
                    resource_package, f"prompts/{entry.name}"
                ),
                text=text,
                canonical_name=entry.name,
                source_kind="built_in",
                source_scope="builtin",
                source="package_resource",
                source_root=_package_source_root_path(resource_package, "prompts"),
                source_root_order=source_root_order,
            )
            diagnostics.extend(frontmatter_diagnostics)
            if descriptor is not None:
                descriptors.append(descriptor)
            continue
        diagnostics.append(
            resource_diagnostic(
                code="unsupported_prompt_entry",
                message="Built-in prompt entries must be .md files.",
                source_path=_package_resource_path(
                    resource_package, f"prompts/{entry.name}"
                ),
                resource_type="prompt",
                source_kind="built_in",
            )
        )
    return descriptors, diagnostics


def _discover_built_in_skills(
    resource_package: str,
    *,
    source_root_order: int,
) -> tuple[list[SkillDescriptor], list[DiagnosticDraft]]:
    skills_root = _built_in_category_root(resource_package, "skills")
    if skills_root is None:
        return [], []

    descriptors: list[SkillDescriptor] = []
    diagnostics: list[DiagnosticDraft] = []
    for entry in _iter_built_in_entries(skills_root):
        if not entry.is_dir():
            diagnostics.append(
                resource_diagnostic(
                    code="unsupported_skill_entry",
                    message="Built-in skill entries must be directories.",
                    source_path=_package_resource_path(
                        resource_package, f"skills/{entry.name}"
                    ),
                    resource_type="skill",
                    source_kind="built_in",
                )
            )
            continue

        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            diagnostics.append(
                resource_diagnostic(
                    code="missing_skill_entry",
                    message="Built-in skill directories must contain SKILL.md.",
                    source_path=_package_resource_path(
                        resource_package, f"skills/{entry.name}"
                    ),
                    resource_type="skill",
                    source_kind="built_in",
                )
            )
            continue

        content, read_diagnostics = _read_text_resource(
            skill_file,
            resource_package=resource_package,
            relative_path=f"skills/{entry.name}/SKILL.md",
            diagnostic_code="unreadable_skill_entry",
            message_prefix="Failed to read built-in skill entry",
        )
        diagnostics.extend(read_diagnostics)
        if content is None:
            continue
        source_path = _package_resource_path(
            resource_package, f"skills/{entry.name}/SKILL.md"
        )
        descriptor, parsing_diagnostics = _skill_descriptor_from_text(
            parent_name=entry.name,
            source_path=source_path,
            content=content,
            canonical_name=f"{entry.name}/SKILL.md",
            source_kind="built_in",
            source_scope="builtin",
            source="package_resource",
            source_root=_package_source_root_path(resource_package, "skills"),
            source_root_order=source_root_order,
        )
        diagnostics.extend(parsing_diagnostics)
        if descriptor is not None:
            descriptors.append(descriptor)
    return descriptors, diagnostics


def _discover_built_in_extensions(
    resource_package: str,
    *,
    source_root_order: int,
) -> tuple[list[ExtensionDescriptor], list[DiagnosticDraft]]:
    extensions_root = _built_in_category_root(resource_package, "extensions")
    if extensions_root is None:
        return [], []

    descriptors: list[ExtensionDescriptor] = []
    diagnostics: list[DiagnosticDraft] = []
    for entry in _iter_built_in_entries(extensions_root):
        if entry.is_file() and entry.name.endswith(".py"):
            entry_path = _package_resource_path(
                resource_package, f"extensions/{entry.name}"
            )
            descriptors.append(
                ExtensionDescriptor(
                    name=entry.name.removesuffix(".py"),
                    source_path=entry_path,
                    entry_path=entry_path,
                    canonical_name=entry.name,
                    source_kind="built_in",
                    source_scope="builtin",
                    source="package_resource",
                    source_root=_package_source_root_path(
                        resource_package, "extensions"
                    ),
                    source_root_order=source_root_order,
                )
            )
            continue
        if entry.is_dir():
            entry_name = _find_extension_entry_name(entry)
            if entry_name is None:
                diagnostics.append(
                    resource_diagnostic(
                        code="missing_extension_entry",
                        message="Built-in extension directories must contain extension.py or __init__.py.",
                        source_path=_package_resource_path(
                            resource_package, f"extensions/{entry.name}"
                        ),
                        resource_type="extension",
                        source_kind="built_in",
                    )
                )
                continue
            descriptors.append(
                ExtensionDescriptor(
                    name=entry.name,
                    source_path=_package_resource_path(
                        resource_package, f"extensions/{entry.name}"
                    ),
                    entry_path=_package_resource_path(
                        resource_package,
                        f"extensions/{entry.name}/{entry_name}",
                    ),
                    canonical_name=entry.name,
                    source_kind="built_in",
                    source_scope="builtin",
                    source="package_resource",
                    source_root=_package_source_root_path(
                        resource_package, "extensions"
                    ),
                    source_root_order=source_root_order,
                )
            )
            continue
        diagnostics.append(
            resource_diagnostic(
                code="unsupported_extension_entry",
                message="Built-in extension entries must be .py files or directories.",
                source_path=_package_resource_path(
                    resource_package, f"extensions/{entry.name}"
                ),
                resource_type="extension",
                source_kind="built_in",
            )
        )
    return descriptors, diagnostics


def _discover_built_in_themes(
    resource_package: str,
    *,
    source_root_order: int,
) -> tuple[list[ThemeDescriptor], list[DiagnosticDraft]]:
    themes_root = _built_in_category_root(resource_package, "themes")
    if themes_root is None:
        return [], []

    descriptors = [
        ThemeDescriptor(
            name=entry.name.removesuffix(".json") if entry.is_file() else entry.name,
            source_path=_package_resource_path(
                resource_package, f"themes/{entry.name}"
            ),
            canonical_name=entry.name,
            source_kind="built_in",
            source_scope="builtin",
            source="package_resource",
            source_root=_package_source_root_path(resource_package, "themes"),
            source_root_order=source_root_order,
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


def _built_in_category_root(resource_package: str, category: str) -> Traversable | None:
    try:
        root = resources.files(resource_package)
    except ModuleNotFoundError:
        return None
    category_root = root / category
    if not category_root.is_dir():
        return None
    return category_root


def _find_extension_entry_name(entry: Traversable) -> str | None:
    for filename in ("extension.py", "__init__.py"):
        candidate = entry / filename
        if candidate.is_file():
            return filename
    return None


def _read_text_resource(
    resource: Traversable,
    *,
    resource_package: str,
    relative_path: str,
    diagnostic_code: str,
    message_prefix: str,
) -> tuple[str | None, list[DiagnosticDraft]]:
    logical_path = _package_resource_path(resource_package, relative_path)
    try:
        return resource.read_text(encoding="utf-8").strip(), []
    except OSError as exc:
        return (
            None,
            [
                resource_diagnostic(
                    code=diagnostic_code,
                    message=f"{message_prefix}: {exc}",
                    source_path=logical_path,
                    source_kind="built_in",
                )
            ],
        )


def _package_resource_path(resource_package: str, relative_path: str) -> Path:
    return Path(resource_package.replace(".", "/")) / relative_path


def _package_source_root_path(resource_package: str, category: str) -> Path:
    return Path(resource_package.replace(".", "/")) / category


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
