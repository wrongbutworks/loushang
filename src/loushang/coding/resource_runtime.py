from __future__ import annotations

from pathlib import Path
from typing import Any

from loushang.harness.resources.loader import (
    DEFAULT_CONTEXT_FILE_NAMES,
    ProfiledResourceLoader,
    ResourceLoader,
    ResourceLoaderProfile,
)
from loushang.harness.resources.packages.materializer import (
    PackageMaterializer,
    PackageSourcePolicy,
)
from loushang.harness.resources.skills import SkillLoader
from loushang.harness.resources.types import ResourceBundle

BUILT_IN_RESOURCE_PACKAGE = "loushang.coding.resources"
CODING_CONTEXT_FILE_NAMES = (*DEFAULT_CONTEXT_FILE_NAMES, "CLAUDE.md", "CLAUDE.MD")


def _assemble_coding_system_prompt(
    base_prompt: str | None,
    resource_bundle: ResourceBundle,
) -> str | None:
    from loushang.coding.prompt import assemble_system_prompt

    system_prompt = assemble_system_prompt(
        base_prompt=base_prompt,
        resource_bundle=resource_bundle,
    )
    return system_prompt or None


CODING_RESOURCE_PROFILE = ResourceLoaderProfile(
    built_in_resource_packages=(BUILT_IN_RESOURCE_PACKAGE,),
    context_file_names=CODING_CONTEXT_FILE_NAMES,
    user_resource_roots=(),
    project_resource_mode="legacy",
    system_prompt_assembler=_assemble_coding_system_prompt,
)


class CodingResourceLoader(ProfiledResourceLoader):
    """Shared resource loader bound to Coding content and prompt semantics."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, profile=CODING_RESOURCE_PROFILE, **kwargs)


class CodingPackageMaterializer(PackageMaterializer):
    """Harness package materializer with Coding's package-security policy."""

    def __init__(
        self,
        *,
        security_policy: PackageSourcePolicy | None = None,
        **kwargs: Any,
    ) -> None:
        if security_policy is None:
            from loushang.coding.policy.package_security import PackageSecurityPolicy

            security_policy = PackageSecurityPolicy()
        super().__init__(
            security_policy=security_policy,
            **kwargs,
        )


class CodingSkillLoader(SkillLoader):
    """Harness skill loader with Coding's built-in resource content."""

    def __init__(
        self,
        *,
        resource_loader: ResourceLoader | None = None,
        package_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            resource_loader=resource_loader
            or CodingResourceLoader(package_roots=package_roots),
            **kwargs,
        )


__all__ = [
    "BUILT_IN_RESOURCE_PACKAGE",
    "CODING_CONTEXT_FILE_NAMES",
    "CODING_RESOURCE_PROFILE",
    "CodingPackageMaterializer",
    "CodingResourceLoader",
    "CodingSkillLoader",
]
