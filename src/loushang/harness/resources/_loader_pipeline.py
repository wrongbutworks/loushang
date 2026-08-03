"""Resource discovery, resolution, diagnostics, and snapshot assembly pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loushang.harness.diagnostics.types import DiagnosticDraft
from loushang.harness.resources._loader_discovery import (
    _apply_resource_switches,
    _discover_built_in_resources,
    _discover_context_descriptors,
    _discover_external_package_resources,
    _discover_project_resources,
    _discover_temporary_resources,
    _discover_user_global_resources,
)
from loushang.harness.resources._loader_resolution import (
    _resolve_candidates,
    _resolve_extension_candidates,
    _resolve_strict_named_candidates,
)
from loushang.harness.resources._loader_types import DEFAULT_CONTEXT_FILE_NAMES
from loushang.harness.resources.types import (
    PromptFragmentDescriptor,
    ResourceSnapshot,
    ResourceSourceKind,
)

if TYPE_CHECKING:
    from loushang.harness.resources.packages.source import PackageSourceConfig


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
    built_in_resource_packages: tuple[str, ...] = (),
    context_file_names: tuple[str, ...] = DEFAULT_CONTEXT_FILE_NAMES,
    project_resource_root: Path | None = None,
) -> ResourceSnapshot:
    target = Path(cwd)
    context_descriptors: list[PromptFragmentDescriptor]
    agents_descriptor: PromptFragmentDescriptor | None
    context_diagnostics: list[DiagnosticDraft]
    if no_context_files:
        context_descriptors, agents_descriptor, context_diagnostics = [], None, []
    else:
        context_descriptors, agents_descriptor, context_diagnostics = (
            _discover_context_descriptors(
                target,
                user_resource_roots=user_resource_roots,
                context_file_names=context_file_names,
            )
        )
    project_context_descriptors = [
        descriptor
        for descriptor in context_descriptors
        if descriptor.source_kind == "project_local"
    ]
    project_root = (
        project_context_descriptors[-1].source_path.parent
        if project_context_descriptors
        else (target if target.is_dir() else target.parent)
    )
    if project_resource_root is not None:
        project_root = project_resource_root

    built_in = _apply_resource_switches(
        _discover_built_in_resources(built_in_resource_packages),
        no_prompts=no_prompt_templates,
        no_skills=no_skills,
        no_extensions=no_extensions,
        no_themes=no_themes,
    )
    external = _apply_resource_switches(
        _discover_external_package_resources(
            package_roots, package_source_filters=package_source_filters
        ),
        no_prompts=no_prompt_templates,
        no_skills=no_skills,
        no_extensions=no_extensions,
        no_themes=no_themes,
    )
    user_global = _apply_resource_switches(
        _discover_user_global_resources(
            user_resource_roots, explicit_roots=explicit_user_roots
        ),
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

    active_prompts, prompt_diagnostics, prompt_decisions = (
        _resolve_strict_named_candidates(
            [
                *temporary.prompts,
                *built_in.prompts,
                *external.prompts,
                *user_global.prompts,
                *project.prompts,
            ],
            resource_type="prompt",
        )
    )
    active_skills, skill_diagnostics, skill_decisions = (
        _resolve_strict_named_candidates(
            [
                *temporary.skills,
                *built_in.skills,
                *external.skills,
                *user_global.skills,
                *project.skills,
            ],
            resource_type="skill",
        )
    )
    active_extensions, extension_diagnostics, extension_decisions = (
        _resolve_extension_candidates(
            [
                *temporary.extensions,
                *built_in.extensions,
                *external.extensions,
                *user_global.extensions,
                *project.extensions,
            ],
            resource_type="extension",
        )
    )
    active_themes, theme_diagnostics, theme_decisions = _resolve_candidates(
        [
            *temporary.themes,
            *built_in.themes,
            *external.themes,
            *user_global.themes,
            *project.themes,
        ],
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
            has_built_in=bool(built_in_resource_packages),
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
        candidate_prompt_descriptors=tuple(
            [
                *temporary.prompts,
                *built_in.prompts,
                *external.prompts,
                *user_global.prompts,
                *project.prompts,
            ]
        ),
        active_skill_descriptors=tuple(active_skills),
        candidate_skill_descriptors=tuple(
            [
                *temporary.skills,
                *built_in.skills,
                *external.skills,
                *user_global.skills,
                *project.skills,
            ]
        ),
        active_extension_descriptors=tuple(active_extensions),
        candidate_extension_descriptors=tuple(
            [
                *temporary.extensions,
                *built_in.extensions,
                *external.extensions,
                *user_global.extensions,
                *project.extensions,
            ]
        ),
        active_theme_descriptors=tuple(active_themes),
        candidate_theme_descriptors=tuple(
            [
                *temporary.themes,
                *built_in.themes,
                *external.themes,
                *user_global.themes,
                *project.themes,
            ]
        ),
        diagnostics=tuple(diagnostics),
        merge_decisions=tuple(merge_decisions),
    )


def _source_kinds_for(
    package_roots: tuple[Path, ...],
    user_resource_roots: tuple[Path, ...] = (),
    *,
    has_built_in: bool = False,
    has_temporary: bool = False,
) -> tuple[ResourceSourceKind, ...]:
    kinds: list[ResourceSourceKind] = []
    if has_temporary:
        kinds.append("temporary")
    if has_built_in:
        kinds.append("built_in")
    if user_resource_roots:
        kinds.append("user_global")
    if package_roots:
        kinds.append("external_package")
    kinds.append("project_local")
    return tuple(kinds)
