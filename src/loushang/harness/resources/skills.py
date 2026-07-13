from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from loushang.harness.resources.loader import ResourceLoader
from loushang.harness.resources.types import SkillDescriptor

SettingsScope = Literal["session", "global", "project"]


class SkillSettingsManager(Protocol):
    def get_disabled_skills(self) -> list[str]: ...

    def set_disabled_skills(
        self, names: list[str], *, scope: SettingsScope = "project"
    ) -> None: ...

    def enable_skill(self, name: str, *, scope: SettingsScope = "project") -> None: ...

    def disable_skill(self, name: str, *, scope: SettingsScope = "project") -> None: ...


class SkillLoader:
    """Skill-specific facade over the resource loader skill discovery rules."""

    def __init__(
        self,
        *,
        resource_loader: ResourceLoader | None = None,
        package_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
        disabled_skills: list[str] | tuple[str, ...] | None = None,
        settings_manager: SkillSettingsManager | None = None,
        settings_scope: SettingsScope = "project",
    ) -> None:
        self._resource_loader = resource_loader or ResourceLoader(
            package_roots=package_roots
        )
        self._cwd: Path | None = None
        self._disabled: set[str] = set(disabled_skills or ())
        self._settings_manager = settings_manager
        self._settings_scope = settings_scope

    def discover_skills(self, cwd: str | Path) -> list[SkillDescriptor]:
        self._cwd = Path(cwd)
        self._resource_loader.discover_resources(self._cwd)
        return self.list_enabled_skills()

    def reload_skills(self, cwd: str | Path | None = None) -> list[SkillDescriptor]:
        if cwd is not None:
            return self.discover_skills(cwd)
        if self._cwd is None:
            return self.discover_skills(Path.cwd())
        self._resource_loader.reload_resources(self._cwd)
        return self.list_enabled_skills()

    def load_skill(self, name: str) -> SkillDescriptor:
        skill = self.get_skill(name)
        if skill is None:
            raise KeyError(name)
        return skill

    def get_skill(self, name: str) -> SkillDescriptor | None:
        for skill in self.list_skills():
            if _matches_skill(skill, name):
                return skill
        return None

    def list_skills(self) -> list[SkillDescriptor]:
        snapshot = self._resource_loader.get_resource_snapshot()
        return list(snapshot.active_skill_descriptors)

    def list_enabled_skills(self) -> list[SkillDescriptor]:
        disabled = self._disabled_names()
        return [
            skill
            for skill in self.list_skills()
            if not _is_disabled_skill(skill, disabled)
        ]

    def enable_skill(self, name: str) -> SkillDescriptor:
        skill = self.load_skill(name)
        self._disabled.discard(_skill_key(skill))
        if self._settings_manager is not None:
            next_disabled = [
                disabled_name
                for disabled_name in self._settings_manager.get_disabled_skills()
                if not _matches_skill(skill, disabled_name)
            ]
            self._settings_manager.set_disabled_skills(
                next_disabled, scope=self._settings_scope
            )
        return skill

    def disable_skill(self, name: str) -> SkillDescriptor:
        skill = self.load_skill(name)
        self._disabled.add(_skill_key(skill))
        if self._settings_manager is not None:
            self._settings_manager.disable_skill(skill.name, scope=self._settings_scope)
        return skill

    def _disabled_names(self) -> set[str]:
        disabled = set(self._disabled)
        if self._settings_manager is not None:
            disabled.update(self._settings_manager.get_disabled_skills())
        return disabled


def _matches_skill(skill: SkillDescriptor, name: str) -> bool:
    return name in {
        skill.name,
        skill.id,
        skill.canonical_name,
        str(skill.source_path),
    }


def _skill_key(skill: SkillDescriptor) -> str:
    return skill.id or skill.canonical_name or skill.name


def _is_disabled_skill(skill: SkillDescriptor, disabled: set[str]) -> bool:
    return any(
        value in disabled
        for value in (
            skill.name,
            skill.id,
            skill.canonical_name,
            str(skill.source_path),
        )
    )
