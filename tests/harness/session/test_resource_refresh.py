from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.harness.resources.types import (
    PromptFragmentDescriptor,
    ResourceBundle,
    SkillDescriptor,
)
from loushang.harness.session.resource_refresh import SessionResourceRefreshRuntime


class _Loader:
    def __init__(self, bundle: ResourceBundle | Exception) -> None:
        self.bundle = bundle
        self.calls: list[str] = []

    def reload_resources(self, cwd: str) -> ResourceBundle:
        self.calls.append(cwd)
        if isinstance(self.bundle, Exception):
            raise self.bundle
        return self.bundle


class _ExtensionRuntime:
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


class _AsyncExtensionRuntime:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    async def discover_resources_async(
        self, bundle: ResourceBundle, *, reason: str = "refresh"
    ) -> ResourceBundle:
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

    def reload_resources(self, cwd: str) -> ResourceBundle:
        raise AssertionError(f"unexpected reload for {cwd}")


def _runtime(
    *,
    loader: _Loader | _PromptLoader | None,
    bundle: ResourceBundle | None = None,
    extension_runtime: object | None = None,
    settings: _Settings | None = None,
    refreshed: list[ResourceBundle] | None = None,
    rebuilds: list[str] | None = None,
    failures: list[Exception] | None = None,
    syncs: list[str] | None = None,
) -> SessionResourceRefreshRuntime:
    return SessionResourceRefreshRuntime(
        get_resource_loader=lambda: loader,
        get_resource_bundle=lambda: bundle,
        get_cwd=lambda: "/tmp/project",
        get_extension_runtime=lambda: extension_runtime,
        get_settings=lambda: settings,
        set_resource_bundle=(refreshed if refreshed is not None else []).append,
        rebuild_prompt_and_tools_view=lambda: (
            rebuilds if rebuilds is not None else []
        ).append("rebuild"),
        record_refresh_failure=(failures if failures is not None else []).append,
        sync_extension_diagnostics=lambda: (syncs if syncs is not None else []).append(
            "resource_loading"
        ),
    )


def test_session_resource_refresh_runtime_gets_prompt_templates_from_loader_then_bundle() -> (
    None
):
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

    runtime = _runtime(loader=_PromptLoader([loader_prompt]), bundle=bundle)
    fallback_runtime = _runtime(loader=None, bundle=bundle)

    assert runtime.get_prompt_templates() == [loader_prompt]
    assert fallback_runtime.get_prompt_templates() == [bundle_prompt]


def test_session_resource_refresh_runtime_reloads_discovers_disables_and_rebuilds() -> (
    None
):
    refreshed: list[ResourceBundle] = []
    rebuilds: list[str] = []
    extension_runtime = _ExtensionRuntime()
    loader = _Loader(
        ResourceBundle(
            cwd=Path("/tmp/project"),
            prompt_fragments=["runtime prompt"],
            skills=[
                SkillDescriptor(
                    name="enabled-skill",
                    source_path=Path("/tmp/project/skills/enabled/SKILL.md"),
                ),
                SkillDescriptor(
                    name="disabled-skill",
                    source_path=Path("/tmp/project/skills/disabled/SKILL.md"),
                ),
            ],
        )
    )
    runtime = _runtime(
        loader=loader,
        extension_runtime=extension_runtime,
        settings=_Settings(),
        refreshed=refreshed,
        rebuilds=rebuilds,
    )

    runtime.refresh()

    assert loader.calls == ["/tmp/project"]
    assert len(extension_runtime.calls) == 1
    assert len(refreshed) == 1
    bundle = refreshed[0]
    assert bundle.prompt_fragments == ["runtime prompt", "extension refresh prompt"]
    assert [descriptor.name for descriptor in bundle.prompt_descriptors] == [
        "runtime-reload-0",
        "extension-refresh",
    ]
    assert [skill.enabled for skill in bundle.skills] == [True, False]
    assert rebuilds == ["rebuild"]


def test_session_resource_refresh_runtime_awaits_async_extension_discovery() -> None:
    refreshed: list[ResourceBundle] = []
    rebuilds: list[str] = []
    extension_runtime = _AsyncExtensionRuntime()
    loader = _Loader(
        ResourceBundle(cwd=Path("/tmp/project"), prompt_fragments=["runtime prompt"])
    )
    runtime = _runtime(
        loader=loader,
        extension_runtime=extension_runtime,
        refreshed=refreshed,
        rebuilds=rebuilds,
    )

    asyncio.run(runtime.refresh_async(reason="reload"))

    assert extension_runtime.reasons == ["reload"]
    assert len(refreshed) == 1
    assert refreshed[0].prompt_fragments == [
        "runtime prompt",
        "async extension refresh prompt",
    ]
    assert rebuilds == ["rebuild"]


def test_session_resource_refresh_runtime_request_records_failures_once() -> None:
    failures: list[Exception] = []
    syncs: list[str] = []
    runtime = _runtime(
        loader=_Loader(RuntimeError("reload boom")),
        failures=failures,
        syncs=syncs,
    )

    runtime.request_refresh()

    assert [str(error) for error in failures] == ["reload boom"]
    assert syncs == []


def test_session_resource_refresh_runtime_request_without_loader_is_a_no_op() -> None:
    syncs: list[str] = []
    runtime = _runtime(loader=None, syncs=syncs)

    runtime.request_refresh()

    assert syncs == []
