from __future__ import annotations

import asyncio


class _Lifecycle:
    active = True
    active_id = 5
    aborted_id: int | None = None

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def mark_abort_requested(self) -> None:
        self.calls.append("mark_abort_requested")
        self.aborted_id = self.active_id


class _Renderer:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def render_interruption(self) -> None:
        self.calls.append("render_interruption")


class _Controller:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def dispatch(self, intent) -> None:
        self.calls.append(f"dispatch:{type(intent).__name__}")


def test_abort_handler_marks_and_renders_interruption_before_dispatch() -> None:
    from loushang.coding.interaction.plain_abort import AbortHandler

    calls: list[str] = []
    traces: list[tuple[str, dict[str, object]]] = []

    async def emit(write, *, label: str) -> None:
        calls.append(f"emit:{label}")
        write()

    handler = AbortHandler(
        lifecycle=_Lifecycle(calls),
        controller=_Controller(calls),
        renderer=_Renderer(calls),
        emit=emit,
        session_running=lambda: False,
        trace=lambda name, **data: traces.append((name, data)),
    )

    asyncio.run(handler.abort())

    assert calls == [
        "mark_abort_requested",
        "emit:abort:interruption",
        "render_interruption",
        "dispatch:AbortIntent",
    ]
    assert traces == [
        (
            "abort.start",
            {
                "active_run": True,
                "active_run_id": 5,
                "aborted_run_id": None,
                "session_running": False,
            },
        ),
        (
            "abort.end",
            {
                "active_run": True,
                "active_run_id": 5,
                "aborted_run_id": 5,
                "session_running": False,
            },
        ),
    ]
