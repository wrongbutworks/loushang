from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any


def test_event_stream_handler_emits_transcript_events_through_stable_emitter() -> None:
    from loushang.coding.ui.event_stream import CodingUiEventStreamHandler

    rendered: list[dict[str, Any]] = []
    emitted: list[str] = []
    traces: list[str] = []

    class Renderer:
        def handle(self, event: dict[str, Any]) -> None:
            rendered.append(event)

    async def emit(write_callable, *, label: str) -> None:
        emitted.append(label)
        write_callable()

    handler = CodingUiEventStreamHandler(
        renderer=Renderer(),
        emit=emit,
        trace=lambda name, **_data: traces.append(name),
    )

    event = {"type": "message_end", "message": SimpleNamespace(role="assistant")}
    asyncio.run(handler.handle(event))

    assert emitted == ["event:message_end"]
    assert rendered == [event]
    assert traces == ["event.start", "event.end"]


def test_event_stream_handler_renders_non_transcript_events_directly() -> None:
    from loushang.coding.ui.event_stream import CodingUiEventStreamHandler

    rendered: list[dict[str, Any]] = []
    emitted: list[str] = []

    class Renderer:
        def handle(self, event: dict[str, Any]) -> None:
            rendered.append(event)

    async def emit(write_callable, *, label: str) -> None:
        emitted.append(label)
        write_callable()

    handler = CodingUiEventStreamHandler(
        renderer=Renderer(),
        emit=emit,
        trace=lambda _name, **_data: None,
    )

    asyncio.run(handler.handle({"type": "message_update"}))

    assert emitted == []
    assert rendered == [{"type": "message_update"}]


def test_event_stream_handler_traces_end_when_rendering_raises() -> None:
    from loushang.coding.ui.event_stream import CodingUiEventStreamHandler

    traces: list[tuple[str, dict[str, object]]] = []

    class Renderer:
        def handle(self, event: dict[str, Any]) -> None:
            raise RuntimeError("render failed")

    async def emit(write_callable, *, label: str) -> None:
        write_callable()

    handler = CodingUiEventStreamHandler(
        renderer=Renderer(),
        emit=emit,
        trace=lambda name, **data: traces.append((name, data)),
    )

    try:
        asyncio.run(handler.handle({"type": "tool_execution_end"}))
    except RuntimeError as error:
        assert str(error) == "render failed"
    else:
        raise AssertionError("expected RuntimeError")

    assert [name for name, _ in traces] == ["event.start", "event.end"]
    assert traces[-1][1]["event_type"] == "tool_execution_end"
