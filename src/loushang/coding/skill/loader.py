from __future__ import annotations

from pathlib import Path

from loushang.coding.loader import DefaultResourceLoader
from loushang.harness.resources.loader import ResourceLoader
from loushang.harness.resources.skills import (
    SettingsScope,
    SkillSettingsManager,
)
from loushang.harness.resources.skills import (
    SkillLoader as HarnessSkillLoader,
)


class SkillLoader(HarnessSkillLoader):
    """Coding facade that registers Coding's built-in resource package."""

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
            or DefaultResourceLoader(package_roots=package_roots),
            disabled_skills=disabled_skills,
            settings_manager=settings_manager,
            settings_scope=settings_scope,
        )


__all__ = ["SettingsScope", "SkillLoader", "SkillSettingsManager"]
