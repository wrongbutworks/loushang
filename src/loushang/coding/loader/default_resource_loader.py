from __future__ import annotations

from pathlib import Path

from loushang.harness.resources.builtin import (
    BuiltInResourcePackage,
    BuiltInResourceRegistry,
)
from loushang.harness.resources.loader import ResourceLoader
from loushang.harness.resources.packages.source import PackageSourceConfig

BUILT_IN_RESOURCE_PACKAGE = "loushang.coding.resources"
CODING_CONTEXT_FILE_NAMES = (
    "AGENTS.md",
    "AGENTS.MD",
    "CLAUDE.md",
    "CLAUDE.MD",
)


class DefaultResourceLoader(ResourceLoader):
    """Coding product facade over the Harness resource runtime."""

    def __init__(
        self,
        package_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
        package_source_filters: dict[str | Path, PackageSourceConfig] | None = None,
        user_resource_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_extension_paths: list[str | Path]
        | tuple[str | Path, ...]
        | None = None,
        additional_skill_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        additional_prompt_template_paths: list[str | Path]
        | tuple[str | Path, ...]
        | None = None,
        additional_theme_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        no_extensions: bool = False,
        no_skills: bool = False,
        no_prompt_templates: bool = False,
        no_themes: bool = False,
        no_context_files: bool = False,
        system_prompt: str | None = None,
        append_system_prompt: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        built_in_registry = BuiltInResourceRegistry()
        built_in_registry.register(
            BuiltInResourcePackage(
                name="coding",
                package=BUILT_IN_RESOURCE_PACKAGE,
            )
        )
        super().__init__(
            package_roots=package_roots,
            package_source_filters=package_source_filters,
            user_resource_roots=()
            if user_resource_roots is None
            else user_resource_roots,
            additional_extension_paths=additional_extension_paths,
            additional_skill_paths=additional_skill_paths,
            additional_prompt_template_paths=additional_prompt_template_paths,
            additional_theme_paths=additional_theme_paths,
            no_extensions=no_extensions,
            no_skills=no_skills,
            no_prompt_templates=no_prompt_templates,
            no_themes=no_themes,
            no_context_files=no_context_files,
            system_prompt=system_prompt,
            append_system_prompt=append_system_prompt,
            built_in_resource_registry=built_in_registry,
            context_file_names=CODING_CONTEXT_FILE_NAMES,
            project_resource_mode="legacy",
        )

    def get_system_prompt(self, *, base_prompt: str | None = None) -> str | None:
        from loushang.coding.prompt import assemble_system_prompt

        system_prompt = assemble_system_prompt(
            base_prompt=base_prompt,
            resource_bundle=self.get_resource_bundle(),
        )
        return system_prompt or None
