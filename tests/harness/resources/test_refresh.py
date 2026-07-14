from __future__ import annotations

import asyncio

import pytest

from loushang.harness.resources.refresh import (
    ResourceRefreshCoordinator,
    RuntimeResourceDiscovery,
)


def test_resource_refresh_coordinator_orders_sync_pipeline() -> None:
    calls: list[object] = []
    coordinator = ResourceRefreshCoordinator[list[str]](
        prepare_refresh=lambda: calls.append("prepare"),
        load_resource=lambda: calls.append("load") or ["base"],
        discover_resource=lambda resource, reason: (
            calls.append(("discover", list(resource), reason))
            or [*resource, "extension"]
        ),
        commit_resource=lambda resource: calls.append(("commit", list(resource))),
    )

    result = coordinator.refresh(reason="watch")

    assert result == ["base", "extension"]
    assert calls == [
        "prepare",
        "load",
        ("discover", ["base"], "watch"),
        ("commit", ["base", "extension"]),
    ]


def test_resource_refresh_coordinator_awaits_async_pipeline() -> None:
    calls: list[object] = []

    async def prepare() -> None:
        await asyncio.sleep(0)
        calls.append("prepare")

    async def discover(resource: str, reason: str) -> str:
        await asyncio.sleep(0)
        calls.append(("discover", resource, reason))
        return f"{resource}:discovered"

    async def commit(resource: str) -> None:
        await asyncio.sleep(0)
        calls.append(("commit", resource))

    coordinator = ResourceRefreshCoordinator(
        prepare_refresh=prepare,
        load_resource=lambda: calls.append("load") or "base",
        discover_resource_async=discover,
        commit_resource=commit,
    )

    result = asyncio.run(coordinator.refresh_async(reason="reload"))

    assert result == "base:discovered"
    assert calls == [
        "prepare",
        "load",
        ("discover", "base", "reload"),
        ("commit", "base:discovered"),
    ]


def test_resource_refresh_coordinator_rejects_async_sync_driver() -> None:
    async def discover(resource: str, reason: str) -> str:
        del reason
        return resource

    coordinator = ResourceRefreshCoordinator(
        load_resource=lambda: "base",
        discover_resource=discover,
        commit_resource=lambda resource: None,
    )

    with pytest.raises(TypeError, match="use refresh_async"):
        coordinator.refresh()


def test_resource_refresh_coordinator_rejects_async_loader_in_sync_mode() -> None:
    async def load() -> str:
        return "base"

    coordinator = ResourceRefreshCoordinator(
        load_resource=load,
        commit_resource=lambda resource: None,
    )

    with pytest.raises(TypeError, match="use refresh_async"):
        coordinator.refresh()

    assert asyncio.run(coordinator.refresh_async()) == "base"


def test_runtime_resource_discovery_supports_legacy_and_async_drivers() -> None:
    class LegacyRuntime:
        def discover_resources(self, resource: str) -> str:
            return f"{resource}:legacy"

    class AsyncRuntime:
        async def discover_resources_async(self, resource: str, *, reason: str) -> str:
            await asyncio.sleep(0)
            return f"{resource}:{reason}"

    runtime: object = LegacyRuntime()
    discovery = RuntimeResourceDiscovery[str](lambda: runtime)

    assert discovery.discover("base", "watch") == "base:legacy"
    runtime = AsyncRuntime()
    assert asyncio.run(discovery.discover_async("base", "reload")) == "base:reload"
