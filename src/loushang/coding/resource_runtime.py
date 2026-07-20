from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from loushang.harness.resources.builtin import (
    BuiltInResourcePackage,
    BuiltInResourceRegistry,
)
from loushang.harness.resources.loader import (
    DEFAULT_CONTEXT_FILE_NAMES,
    ResourceLoader,
)
from loushang.harness.resources.packages.materializer import (
    PackageMaterializer,
    PackageMaterializerBackend,
    PackageProgressEvent,
    PackageSourcePolicy,
)
from loushang.harness.resources.packages.source import PackageSourceConfig
from loushang.harness.resources.skills import (
    SettingsScope,
    SkillLoader,
    SkillSettingsManager,
)

BUILT_IN_RESOURCE_PACKAGE = "loushang.coding.resources"
CODING_CONTEXT_FILE_NAMES = (*DEFAULT_CONTEXT_FILE_NAMES, "CLAUDE.md", "CLAUDE.MD")


class CodingResourceLoader(ResourceLoader):
    """Harness resource loader bound to Coding content and prompt semantics."""

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


class CodingPackageMaterializer(PackageMaterializer):
    """Harness package materializer with Coding's package-security policy."""

    def __init__(
        self,
        *,
        install_root: str | Path,
        backend: PackageMaterializerBackend | None = None,
        python_backend: PackageMaterializerBackend | None = None,
        security_policy: PackageSourcePolicy | None = None,
        lockfile_path: str | Path | None = None,
        update_concurrency: int = 4,
        check_concurrency: int = 4,
        update_check_timeout_seconds: float = 10.0,
        progress_callback: Callable[[PackageProgressEvent], None] | None = None,
    ) -> None:
        if security_policy is None:
            from loushang.coding.policy.package_security import PackageSecurityPolicy

            security_policy = PackageSecurityPolicy()
        super().__init__(
            install_root=install_root,
            backend=backend,
            python_backend=python_backend,
            security_policy=security_policy,
            lockfile_path=lockfile_path,
            update_concurrency=update_concurrency,
            check_concurrency=check_concurrency,
            update_check_timeout_seconds=update_check_timeout_seconds,
            progress_callback=progress_callback,
        )


class CodingSkillLoader(SkillLoader):
    """Harness skill loader with Coding's built-in resource content."""

    def __init__(
        self,
        *,
        resource_loader: ResourceLoader | None = None,
        package_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
        disabled_skills: list[str] | tuple[str, ...] | None = None,
        settings_manager: SkillSettingsManager | None = None,
        settings_scope: SettingsScope = "project",
    ) -> None:
        super().__init__(
            resource_loader=resource_loader
            or CodingResourceLoader(package_roots=package_roots),
            disabled_skills=disabled_skills,
            settings_manager=settings_manager,
            settings_scope=settings_scope,
        )


__all__ = [
    "BUILT_IN_RESOURCE_PACKAGE",
    "CODING_CONTEXT_FILE_NAMES",
    "CodingPackageMaterializer",
    "CodingResourceLoader",
    "CodingSkillLoader",
]
