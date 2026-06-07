from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.coding.loader import (
    PromptFragmentDescriptor,
    ResourceBundle,
    ResourceDiagnostic,
    SkillDescriptor,
)
from loushang.coding.session.resource_refresh_controller import (
    ResourceRefreshController,
)


class _Loader:
    def __init__(self, bundle: ResourceBundle | Exception) -> None:
        self.bundle = bundle
        self.calls: list[str] = []

    def reload_resources(self, cwd: str) -> ResourceBundle:
        self.calls.append(cwd)
        if isinstance(self.bundle, Exception):
            raise self.bundle
        return self.bundle


class _ExtensionRunner:
    def __init__(self) -> None:
        self.calls: list[ResourceBundle] = []

    def discover_resources(self, bundle: ResourceBundle) -> ResourceBundle:
        self.calls.append(bundle)
        return bundle.merge(
            prompts=[
                PromptFragmentDescriptor(
                    name="extension-refresh",
                    source_path=Path("/tmp/extension/prompts/refresh.md"),
                    text="extension refresh prompt",
                )
            ]
        )


class _AsyncExtensionRunner:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    async def discover_resources_async(self, bundle: ResourceBundle, *, reason: str = "refresh") -> ResourceBundle:
        self.reasons.append(reason)
        await asyncio.sleep(0)
        return bundle.merge(
            prompts=[
                PromptFragmentDescriptor(
                    name="extension-refresh",
                    source_path=Path("/tmp/extension/prompts/async.md"),
                    text="async extension refresh prompt",
                )
            ]
        )


class _Settings:
    def get_disabled_skills(self) -> list[str]:
        return ["disabled-skill"]


class _PromptLoader:
    def __init__(self, prompts: object) -> None:
        self.prompts = prompts

    def get_prompts(self) -> dict[str, object]:
        return {"prompts": self.prompts}


def test_resource_refresh_controller_gets_prompt_templates_from_loader_then_bundle() -> None:
    loader_prompt = PromptFragmentDescriptor(
        name="loader-prompt",
        source_path=Path("/tmp/project/prompts/loader.md"),
        text="loader prompt",
    )
    bundle_prompt = PromptFragmentDescriptor(
        name="bundle-prompt",
        source_path=Path("/tmp/project/prompts/bundle.md"),
        text="bundle prompt",
    )
    bundle = ResourceBundle(cwd=Path("/tmp/project"), prompts=[bundle_prompt])
    controller = ResourceRefreshController(
        get_resource_loader=lambda: _PromptLoader([loader_prompt]),
        get_resource_bundle=lambda: bundle,
        get_cwd=lambda: "/tmp/project",
        get_extension_runner=lambda: None,
        get_settings_manager=lambda: None,
        set_resource_bundle=lambda resource_bundle: None,
        rebuild_prompt_and_tools_view=lambda: None,
        record_runtime_diagnostic=lambda diagnostic: None,
        sync_extension_diagnostics=lambda **kwargs: None,
    )
    fallback_controller = ResourceRefreshController(
        get_resource_loader=lambda: None,
        get_resource_bundle=lambda: bundle,
        get_cwd=lambda: "/tmp/project",
        get_extension_runner=lambda: None,
        get_settings_manager=lambda: None,
        set_resource_bundle=lambda resource_bundle: None,
        rebuild_prompt_and_tools_view=lambda: None,
        record_runtime_diagnostic=lambda diagnostic: None,
        sync_extension_diagnostics=lambda **kwargs: None,
    )

    assert controller.get_prompt_templates() == [loader_prompt]
    assert fallback_controller.get_prompt_templates() == [bundle_prompt]


def test_resource_refresh_controller_reloads_discovers_disables_and_rebuilds_prompt_view() -> None:
    refreshed: list[ResourceBundle] = []
    rebuilds: list[str] = []
    extension_runner = _ExtensionRunner()
    loader = _Loader(
        ResourceBundle(
            cwd=Path("/tmp/project"),
            prompt_fragments=["runtime prompt"],
            skills=[
                SkillDescriptor(name="enabled-skill", source_path=Path("/tmp/project/skills/enabled/SKILL.md")),
                SkillDescriptor(name="disabled-skill", source_path=Path("/tmp/project/skills/disabled/SKILL.md")),
            ],
        )
    )
    controller = ResourceRefreshController(
        get_resource_loader=lambda: loader,
        get_resource_bundle=lambda: None,
        get_cwd=lambda: "/tmp/project",
        get_extension_runner=lambda: extension_runner,
        get_settings_manager=lambda: _Settings(),
        set_resource_bundle=refreshed.append,
        rebuild_prompt_and_tools_view=lambda: rebuilds.append("rebuild"),
        record_runtime_diagnostic=lambda diagnostic: None,
        sync_extension_diagnostics=lambda **kwargs: None,
    )

    controller.refresh_resources_for_extension_runtime()

    assert loader.calls == ["/tmp/project"]
    assert len(extension_runner.calls) == 1
    assert len(refreshed) == 1
    bundle = refreshed[0]
    assert bundle.prompt_fragments == ["runtime prompt", "extension refresh prompt"]
    assert [descriptor.name for descriptor in bundle.prompt_descriptors] == ["runtime-reload-0", "extension-refresh"]
    assert [skill.enabled for skill in bundle.skills] == [True, False]
    assert rebuilds == ["rebuild"]


def test_resource_refresh_controller_awaits_async_extension_discovery() -> None:
    refreshed: list[ResourceBundle] = []
    rebuilds: list[str] = []
    extension_runner = _AsyncExtensionRunner()
    loader = _Loader(ResourceBundle(cwd=Path("/tmp/project"), prompt_fragments=["runtime prompt"]))
    controller = ResourceRefreshController(
        get_resource_loader=lambda: loader,
        get_resource_bundle=lambda: None,
        get_cwd=lambda: "/tmp/project",
        get_extension_runner=lambda: extension_runner,
        get_settings_manager=lambda: None,
        set_resource_bundle=refreshed.append,
        rebuild_prompt_and_tools_view=lambda: rebuilds.append("rebuild"),
        record_runtime_diagnostic=lambda diagnostic: None,
        sync_extension_diagnostics=lambda **kwargs: None,
    )

    asyncio.run(controller.refresh_resources_for_extension_runtime_async(reason="reload"))

    assert extension_runner.reasons == ["reload"]
    assert len(refreshed) == 1
    assert refreshed[0].prompt_fragments == ["runtime prompt", "async extension refresh prompt"]
    assert rebuilds == ["rebuild"]


def test_resource_refresh_controller_request_records_refresh_failures() -> None:
    records: list[ResourceDiagnostic] = []
    syncs: list[str] = []
    controller = ResourceRefreshController(
        get_resource_loader=lambda: _Loader(RuntimeError("reload boom")),
        get_resource_bundle=lambda: None,
        get_cwd=lambda: "/tmp/project",
        get_extension_runner=lambda: None,
        get_settings_manager=lambda: None,
        set_resource_bundle=lambda bundle: None,
        rebuild_prompt_and_tools_view=lambda: None,
        record_runtime_diagnostic=records.append,
        sync_extension_diagnostics=lambda **kwargs: syncs.append(kwargs["phase"]),
    )

    controller.request_resource_refresh()

    assert [record.code for record in records] == ["extension_resource_refresh_failed"]
    assert "reload boom" in records[0].message
    assert syncs == []
