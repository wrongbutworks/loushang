from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loushang.harness.extensions.lifecycle import (
    ExtensionRuntimeCoordinator,
)


@dataclass(frozen=True)
class ReviewStart:
    reason: str


@dataclass(frozen=True)
class ReviewRefresh:
    reason: str


def test_extension_runtime_coordinator_owns_reload_and_refresh_order() -> None:
    calls: list[object] = []
    coordinator: ExtensionRuntimeCoordinator[dict[str, int], ReviewStart, ReviewRefresh]

    async def refresh_resources() -> None:
        await asyncio.sleep(0)
        calls.append("resources")

    async def emit_start(event: ReviewStart) -> None:
        calls.append(("start", event.reason))

    async def emit_refresh(event: ReviewRefresh) -> None:
        calls.append(("refresh_event", event.reason, coordinator.is_refreshing))

    coordinator = ExtensionRuntimeCoordinator(
        build_bindings=lambda: {"generation": len(calls)},
        bind_runtime=lambda bindings: calls.append(("bind", bindings)),
        refresh_runtime=lambda bindings: calls.append(("refresh_bindings", bindings)),
        emit_session_start=emit_start,
        emit_session_refresh=emit_refresh,
        refresh_resources=refresh_resources,
        record_failure=lambda operation, error: calls.append(
            ("failure", operation, str(error))
        ),
        sync_diagnostics=lambda: calls.append("sync"),
        invalidate_contexts_driver=lambda message: calls.append(
            ("invalidate", message)
        ),
    )

    async def scenario() -> None:
        assert await coordinator.bind(
            ReviewStart("reload"),
            reload=True,
            stale_context_message="stale",
        )
        assert await coordinator.refresh(ReviewRefresh("settings"))

    asyncio.run(scenario())

    assert calls == [
        ("invalidate", "stale"),
        "resources",
        ("bind", {"generation": 2}),
        ("start", "reload"),
        "sync",
        ("refresh_bindings", {"generation": 5}),
        ("refresh_event", "settings", True),
        "sync",
    ]
    assert coordinator.is_refreshing is False


def test_extension_runtime_coordinator_contains_hook_failure_and_syncs() -> None:
    calls: list[object] = []

    async def broken_start(event: ReviewStart) -> None:
        del event
        raise RuntimeError("hook failed")

    coordinator = ExtensionRuntimeCoordinator(
        build_bindings=lambda: "bindings",
        bind_runtime=lambda bindings: calls.append(("bind", bindings)),
        refresh_runtime=lambda bindings: None,
        emit_session_start=broken_start,
        emit_session_refresh=lambda event: None,
        refresh_resources=lambda: None,
        record_failure=lambda operation, error: calls.append((operation, str(error))),
        sync_diagnostics=lambda: calls.append("sync"),
    )

    assert asyncio.run(coordinator.bind(ReviewStart("startup"))) is True
    assert calls == [
        ("bind", "bindings"),
        ("session_start", "hook failed"),
        "sync",
    ]


def test_extension_runtime_coordinator_stops_after_resource_failure() -> None:
    calls: list[object] = []

    def broken_resources() -> None:
        raise RuntimeError("reload failed")

    coordinator = ExtensionRuntimeCoordinator(
        build_bindings=lambda: "bindings",
        bind_runtime=lambda bindings: calls.append(("bind", bindings)),
        refresh_runtime=lambda bindings: None,
        emit_session_start=lambda event: None,
        emit_session_refresh=lambda event: None,
        refresh_resources=broken_resources,
        record_failure=lambda operation, error: calls.append((operation, str(error))),
        sync_diagnostics=lambda: calls.append("sync"),
    )

    assert asyncio.run(coordinator.bind(ReviewStart("reload"), reload=True)) is False
    assert calls == [("resource_refresh", "reload failed")]
