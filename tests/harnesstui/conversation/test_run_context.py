"""Tests for the shared conversation interaction run context."""

from __future__ import annotations

import asyncio

import pytest


def test_interaction_run_context_closes_in_order_and_only_once() -> None:
    from loushang.harnesstui.conversation.run_context import InteractionRunContext

    calls: list[str] = []

    class ExitContext:
        def __exit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback
            calls.append("context.exit")

    async def emit(write_callable, *, label: str) -> None:
        del label
        write_callable()

    context = InteractionRunContext(
        emit=emit,
        _unsubscribe=lambda: calls.append("unsubscribe"),
        _exit_context=ExitContext(),
        _trace=lambda name, **_data: calls.append(name),
    )

    context.close()
    context.close()

    assert calls == ["tui.end", "unsubscribe", "context.exit"]


def test_interaction_run_context_exits_when_trace_or_unsubscribe_fails() -> None:
    from loushang.harnesstui.conversation.run_context import InteractionRunContext

    calls: list[str] = []

    class ExitContext:
        def __exit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback
            calls.append("context.exit")

    def trace(name: str, **_data: object) -> None:
        calls.append(name)
        raise RuntimeError("trace failed")

    context = InteractionRunContext(
        emit=_emit,
        _unsubscribe=lambda: calls.append("unsubscribe"),
        _exit_context=ExitContext(),
        _trace=trace,
    )

    with pytest.raises(RuntimeError, match="trace failed"):
        context.close()

    assert calls == ["tui.end", "unsubscribe", "context.exit"]


def test_stable_emit_factory_traces_success_and_write_error() -> None:
    from loushang.harnesstui.conversation.run_context import stable_emit_factory

    traces: list[tuple[str, dict[str, object]]] = []
    writes: list[str] = []
    emit = stable_emit_factory(
        trace=lambda name, **data: traces.append((name, data)),
        interactive=True,
    )

    asyncio.run(emit(lambda: writes.append("written"), label="event:delta"))

    def fail() -> None:
        raise RuntimeError("write failed")

    with pytest.raises(RuntimeError, match="write failed"):
        asyncio.run(emit(fail, label="event:error"))

    assert writes == ["written"]
    assert [name for name, _data in traces] == [
        "emit.start",
        "emit.end",
        "emit.start",
        "emit.error",
    ]
    assert traces[0][1] == {"label": "event:delta", "interactive": True}
    assert traces[-1][1]["error"] == "write failed"


def test_subscribe_events_uses_returned_hook_or_safe_noop() -> None:
    from loushang.harnesstui.conversation.run_context import subscribe_events

    calls: list[object] = []

    class Source:
        def subscribe(self, listener):
            calls.append(listener)
            return lambda: calls.append("unsubscribe")

    listener = object()
    unsubscribe = subscribe_events(Source(), listener)
    unsubscribe()

    assert calls == [listener, "unsubscribe"]
    assert subscribe_events(object(), listener)() is None


async def _emit(write_callable, *, label: str) -> None:
    del label
    write_callable()
