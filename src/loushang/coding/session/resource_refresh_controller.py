from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.refresh import (
    ResourceRefreshCoordinator,
    RuntimeResourceDiscovery,
)
from loushang.harness.resources.types import (
    PromptFragmentDescriptor,
    ResourceBundle,
    SkillDescriptor,
)


class ResourceLoaderPort(Protocol):
    def reload_resources(self, cwd: str) -> ResourceBundle: ...

    def get_prompts(self) -> dict[str, object]: ...


class ResourceSettingsPort(Protocol):
    def get_disabled_skills(self) -> list[str]: ...


@dataclass
class ResourceRefreshController:
    get_resource_loader: Callable[[], ResourceLoaderPort | None]
    get_resource_bundle: Callable[[], ResourceBundle | None]
    get_cwd: Callable[[], str]
    get_extension_runner: Callable[[], object | None]
    get_settings_manager: Callable[[], ResourceSettingsPort | None]
    set_resource_bundle: Callable[[ResourceBundle], None]
    rebuild_prompt_and_tools_view: Callable[[], None]
    record_runtime_diagnostic: Callable[[ResourceDiagnostic], None]
    sync_extension_diagnostics: Callable[..., None]
    prepare_resource_refresh: Callable[[], None] | None = None
    _coordinator: ResourceRefreshCoordinator[ResourceBundle] = field(init=False)
    _discovery: RuntimeResourceDiscovery[ResourceBundle] = field(init=False)

    def __post_init__(self) -> None:
        self._discovery = RuntimeResourceDiscovery(self.get_extension_runner)
        self._coordinator = ResourceRefreshCoordinator(
            load_resource=self._load_resource_bundle_for_refresh,
            discover_resource=self._discovery.discover,
            discover_resource_async=self._discovery.discover_async,
            commit_resource=self._commit_resource_bundle,
            prepare_refresh=self.prepare_resource_refresh,
        )

    def get_prompt_templates(self) -> list[PromptFragmentDescriptor]:
        resource_loader = self.get_resource_loader()
        if resource_loader is not None:
            get_prompts = getattr(resource_loader, "get_prompts", None)
            if not callable(get_prompts):
                return []
            prompts = get_prompts().get("prompts", [])
            return list(prompts) if isinstance(prompts, list) else []
        resource_bundle = self.get_resource_bundle()
        if resource_bundle is not None:
            return list(resource_bundle.prompts)
        return []

    def refresh_resources_for_extension_runtime(
        self, *, reason: str = "refresh"
    ) -> None:
        self._coordinator.refresh(reason=reason)

    async def refresh_resources_for_extension_runtime_async(
        self, *, reason: str = "refresh"
    ) -> None:
        await self._coordinator.refresh_async(reason=reason)

    def _load_resource_bundle_for_refresh(self) -> ResourceBundle | None:
        resource_loader = self.get_resource_loader()
        if resource_loader is None:
            return None
        resource_bundle = resource_loader.reload_resources(self.get_cwd())
        if resource_bundle.prompt_fragments and not resource_bundle.prompt_descriptors:
            resource_bundle = replace(
                resource_bundle,
                prompt_descriptors=[
                    PromptFragmentDescriptor(
                        name=f"runtime-reload-{index}",
                        source_path=Path(resource_bundle.cwd)
                        / f".loushang-runtime-reload-{index}.md",
                        text=fragment,
                    )
                    for index, fragment in enumerate(resource_bundle.prompt_fragments)
                    if isinstance(fragment, str) and fragment.strip()
                ],
            )
        return resource_bundle

    def _commit_resource_bundle(self, resource_bundle: ResourceBundle) -> None:
        settings_manager = self.get_settings_manager()
        if settings_manager is not None:
            disabled_skills = tuple(settings_manager.get_disabled_skills())
            if disabled_skills:
                resource_bundle = replace(
                    resource_bundle,
                    skills=[
                        replace(skill, enabled=False)
                        if _skill_disabled_by_name(skill, disabled_skills)
                        else skill
                        for skill in resource_bundle.skills
                    ],
                )
        self.set_resource_bundle(resource_bundle)
        self.rebuild_prompt_and_tools_view()

    def request_resource_refresh(self) -> None:
        if self.get_resource_loader() is None:
            return
        try:
            self.refresh_resources_for_extension_runtime()
        except Exception as exc:
            self.record_runtime_diagnostic(
                ResourceDiagnostic(
                    code="extension_resource_refresh_failed",
                    message=f"Extension resource refresh failed: {exc}",
                )
            )
            return
        self.sync_extension_diagnostics(phase="resource_loading")


def _skill_disabled_by_name(
    skill: SkillDescriptor, disabled_skills: tuple[str, ...]
) -> bool:
    return any(
        value in disabled_skills
        for value in (
            skill.name,
            skill.id,
            skill.canonical_name,
            str(skill.source_path),
        )
    )
