from __future__ import annotations

import asyncio
from io import StringIO

import pytest

from loushang.channel import (
    ProductHostAction,
    ProductHostRuntime,
    ProductHostTaskTracker,
    dispatch_product_host_action,
    normalize_product_host_action,
)


class _FakeHostAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.state = {"status": "idle"}

    async def start(self, *args: object, **kwargs: object) -> int:
        self.calls.append(("start", args or kwargs or None))
        return 10

    async def stop(self) -> int:
        self.calls.append(("stop", None))
        return 11

    async def submit_input(self, input_payload: object) -> int:
        self.calls.append(("submit_input", input_payload))
        return 12

    async def wait_for_idle(self) -> int:
        self.calls.append(("wait_for_idle", None))
        return 13

    def rebind_session(self, session: object | None = None) -> int:
        self.calls.append(("rebind_session", session))
        return 14

    async def dispose(self) -> int:
        self.calls.append(("dispose", None))
        return 15

    def render_event(self, event: object) -> None:
        self.calls.append(("render_event", event))


def test_product_host_actions_normalize_and_dispatch_through_injected_state() -> None:
    async def scenario() -> None:
        adapter = _FakeHostAdapter()

        assert normalize_product_host_action({"type": "stop"}) == ProductHostAction(
            "stop"
        )
        assert (
            await dispatch_product_host_action(
                adapter,
                ProductHostAction("start", ("hello",)),
                get_state=lambda host: host.state,
            )
            == 10
        )
        assert (
            await dispatch_product_host_action(
                adapter,
                {"type": "submit_input", "payload": "next"},
                get_state=lambda host: host.state,
            )
            == 12
        )
        assert (
            await dispatch_product_host_action(
                adapter,
                ProductHostAction("render_event", {"type": "notice"}),
                get_state=lambda host: host.state,
            )
            == 0
        )
        assert await dispatch_product_host_action(
            adapter,
            ProductHostAction("get_state"),
            get_state=lambda host: host.state,
        ) == {"status": "idle"}
        assert (
            await dispatch_product_host_action(
                adapter,
                ProductHostAction("dispose"),
                get_state=lambda host: host.state,
            )
            == 15
        )

        assert adapter.calls == [
            ("start", ("hello",)),
            ("submit_input", "next"),
            ("render_event", {"type": "notice"}),
            ("dispose", None),
        ]

    asyncio.run(scenario())


def test_product_host_runtime_stops_after_requested_input_handler() -> None:
    async def scenario() -> None:
        runtime = ProductHostRuntime(stdin=StringIO("first\nstop\nignored\n"))
        seen: list[str] = []
        failures: list[str] = []

        async def handle_input(line: str) -> None:
            seen.append(line.strip())
            if line.strip() == "stop":
                runtime.stop()

        async def handle_failure(error: Exception) -> None:
            failures.append(str(error))

        assert await runtime.run(handle_input, handle_failure=handle_failure) == 0
        assert seen == ["first", "stop"]
        assert failures == []
        assert runtime.is_running is False

    asyncio.run(scenario())


def test_product_host_runtime_reports_terminal_handler_failure() -> None:
    async def scenario() -> None:
        runtime = ProductHostRuntime(stdin=StringIO("request\n"))
        failures: list[str] = []

        async def handle_input(_line: str) -> None:
            raise RuntimeError("dispatch failed")

        assert (
            await runtime.run(
                handle_input,
                handle_failure=lambda error: failures.append(str(error)),
            )
            == 1
        )
        assert failures == ["dispatch failed"]

    asyncio.run(scenario())


def test_product_host_task_tracker_drains_and_discards_completed_tasks() -> None:
    async def scenario() -> None:
        tracker = ProductHostTaskTracker()
        release = asyncio.Event()

        async def run_task() -> str:
            await release.wait()
            return "done"

        task = tracker.track(asyncio.create_task(run_task()))
        release.set()
        await tracker.drain()

        assert await task == "done"

    asyncio.run(scenario())


def test_product_host_action_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unsupported product host action"):
        normalize_product_host_action({"type": "unknown"})
