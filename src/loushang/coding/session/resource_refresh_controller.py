from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.types import (
    PromptFragmentDescriptor,
    ResourceBundle,
    SkillDescriptor,
)


@dataclass
class ResourceRefreshController:
    get_resource_loader: Callable[[], object | None]
    get_resource_bundle: Callable[[], ResourceBundle | None]
    get_cwd: Callable[[], str]
    get_extension_runner: Callable[[], object | None]
    get_settings_manager: Callable[[], object | None]
    set_resource_bundle: Callable[[ResourceBundle], None]
    rebuild_prompt_and_tools_view: Callable[[], None]
    record_runtime_diagnostic: Callable[[ResourceDiagnostic], None]
    sync_extension_diagnostics: Callable[..., None]
    prepare_resource_refresh: Callable[[], None] | None = None

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

    def refresh_resources_for_extension_runtime(self, *, reason: str = "refresh") -> None:
        resource_bundle = self._load_resource_bundle_for_refresh()
        if resource_bundle is None:
            return
        extension_runner = self.get_extension_runner()
        if extension_runner is not None:
            discover_resources = getattr(extension_runner, "discover_resources", None)
            if callable(discover_resources):
                resource_bundle = _call_discover_resources(discover_resources, resource_bundle, reason=reason)
        self._commit_resource_bundle(resource_bundle)

    async def refresh_resources_for_extension_runtime_async(self, *, reason: str = "refresh") -> None:
        resource_bundle = self._load_resource_bundle_for_refresh()
        if resource_bundle is None:
            return
        extension_runner = self.get_extension_runner()
        if extension_runner is not None:
            discover_resources_async = getattr(extension_runner, "discover_resources_async", None)
            if callable(discover_resources_async):
                resource_bundle = await _call_discover_resources_async(
                    discover_resources_async,
                    resource_bundle,
                    reason=reason,
                )
            else:
                discover_resources = getattr(extension_runner, "discover_resources", None)
                if callable(discover_resources):
                    discovered = _call_discover_resources(discover_resources, resource_bundle, reason=reason)
                    if inspect.isawaitable(discovered):
                        discovered = await discovered
                    resource_bundle = discovered
        self._commit_resource_bundle(resource_bundle)

    def _load_resource_bundle_for_refresh(self) -> ResourceBundle | None:
        resource_loader = self.get_resource_loader()
        if resource_loader is None:
            return None
        if self.prepare_resource_refresh is not None:
            self.prepare_resource_refresh()
        resource_bundle = resource_loader.reload_resources(self.get_cwd())
        if resource_bundle.prompt_fragments and not resource_bundle.prompt_descriptors:
            resource_bundle = replace(
                resource_bundle,
                prompt_descriptors=[
                    PromptFragmentDescriptor(
                        name=f"runtime-reload-{index}",
                        source_path=Path(resource_bundle.cwd) / f".loushang-runtime-reload-{index}.md",
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
                        replace(skill, enabled=False) if _skill_disabled_by_name(skill, disabled_skills) else skill
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


def _call_discover_resources(discover_resources: Callable[..., object], bundle: ResourceBundle, *, reason: str) -> ResourceBundle:
    if _accepts_keyword(discover_resources, "reason"):
        return discover_resources(bundle, reason=reason)
    return discover_resources(bundle)


async def _call_discover_resources_async(
    discover_resources: Callable[..., object],
    bundle: ResourceBundle,
    *,
    reason: str,
) -> ResourceBundle:
    if _accepts_keyword(discover_resources, "reason"):
        discovered = discover_resources(bundle, reason=reason)
    else:
        discovered = discover_resources(bundle)
    if inspect.isawaitable(discovered):
        discovered = await discovered
    return discovered


def _accepts_keyword(callback: Callable[..., object], keyword: str) -> bool:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD or name == keyword
        for name, parameter in signature.parameters.items()
    )


def _skill_disabled_by_name(skill: SkillDescriptor, disabled_skills: tuple[str, ...]) -> bool:
    return any(
        value in disabled_skills
        for value in (
            skill.name,
            skill.id,
            skill.canonical_name,
            str(skill.source_path),
        )
    )
