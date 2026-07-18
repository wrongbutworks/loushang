from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def test_open_coding_tui_run_context_enters_subscribes_and_closes_in_order() -> None:
    from loushang.coding.ui.run_context import open_coding_tui_run_context
    from loushang.coding.ui.startup import CodingTuiStartupSnapshot

    calls: list[str] = []
    traces: list[tuple[str, dict[str, object]]] = []

    class ObservabilityContext:
        def __enter__(self):
            calls.append("observability.enter")
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            calls.append("observability.exit")

    class Session:
        def subscribe(self, listener):
            calls.append(f"subscribe:{inspect.iscoroutinefunction(listener)}")

            def unsubscribe() -> None:
                calls.append("unsubscribe")

            return unsubscribe

    snapshot = CodingTuiStartupSnapshot(
        model_label="moonshot/kimi",
        cwd="/repo",
        branch="main",
        project_label="repo",
        session_label="session-name",
        session_observability_id="sid",
    )

    def log_context_factory(**kwargs: Any) -> ObservabilityContext:
        calls.append(f"log_context:{kwargs['session_id']}:{kwargs['cwd']}:{kwargs['mode']}")
        return ObservabilityContext()

    def trace(name: str, **data: Any) -> None:
        traces.append((name, data))

    context = open_coding_tui_run_context(
        session=Session(),
        snapshot=snapshot,
        event_renderer=_EventRenderer(),
        interactive=True,
        log_context_factory=log_context_factory,
        trace=trace,
    )

    assert calls == ["log_context:sid:/repo:tui", "observability.enter", "subscribe:True"]
    assert traces == [
        (
            "tui.start",
            {
                "interactive": True,
                "model": "moonshot/kimi",
                "cwd": "/repo",
                "branch": "main",
                "session": "session-name",
            },
        )
    ]

    context.close()

    assert calls == [
        "log_context:sid:/repo:tui",
        "observability.enter",
        "subscribe:True",
        "unsubscribe",
        "observability.exit",
    ]
    assert traces[-1] == ("tui.end", {})


def test_open_coding_tui_run_context_uses_direct_renderer_for_noninteractive() -> None:
    from loushang.coding.ui.run_context import open_coding_tui_run_context
    from loushang.coding.ui.startup import CodingTuiStartupSnapshot

    listener_kinds: list[bool] = []

    class Session:
        def subscribe(self, listener):
            listener_kinds.append(inspect.iscoroutinefunction(listener))
            return lambda: None

    context = open_coding_tui_run_context(
        session=Session(),
        snapshot=CodingTuiStartupSnapshot(
            model_label=None,
            cwd="/repo",
            branch=None,
            project_label="repo",
            session_label=None,
            session_observability_id=None,
        ),
        event_renderer=_EventRenderer(),
        interactive=False,
        log_context_factory=lambda **_kwargs: _ObservabilityContext(),
        trace=_noop_trace,
    )

    assert listener_kinds == [False]
    context.close()


def test_open_coding_tui_run_context_exits_observability_when_subscribe_fails() -> None:
    from loushang.coding.ui.run_context import open_coding_tui_run_context
    from loushang.coding.ui.startup import CodingTuiStartupSnapshot

    calls: list[str] = []

    class Session:
        def subscribe(self, _listener):
            calls.append("subscribe")
            raise RuntimeError("subscribe exploded")

    class ObservabilityContext:
        def __enter__(self):
            calls.append("observability.enter")
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            calls.append("observability.exit")

    try:
        open_coding_tui_run_context(
            session=Session(),
            snapshot=CodingTuiStartupSnapshot(
                model_label=None,
                cwd="/repo",
                branch=None,
                project_label="repo",
                session_label=None,
                session_observability_id=None,
            ),
            event_renderer=_EventRenderer(),
            interactive=False,
            log_context_factory=lambda **_kwargs: ObservabilityContext(),
            trace=_noop_trace,
        )
    except RuntimeError as error:
        assert str(error) == "subscribe exploded"
    else:
        raise AssertionError("expected subscribe failure")

    assert calls == ["observability.enter", "subscribe", "observability.exit"]


def test_coding_tui_run_context_unsubscribes_when_end_trace_fails() -> None:
    from loushang.coding.ui.run_context import CodingTuiRunContext

    calls: list[str] = []

    class ObservabilityContext:
        def __exit__(self, exc_type, exc, traceback) -> None:
            calls.append("observability.exit")

    def trace(name: str, **_data) -> None:
        calls.append(name)
        raise RuntimeError("trace exploded")

    context = CodingTuiRunContext(
        emit=_emit_in_terminal,
        _unsubscribe=lambda: calls.append("unsubscribe"),
        _observability_context=ObservabilityContext(),
        _trace=trace,
    )

    try:
        context.close()
    except RuntimeError as error:
        assert str(error) == "trace exploded"
    else:
        raise AssertionError("expected trace failure")

    assert calls == ["tui.end", "unsubscribe", "observability.exit"]


def test_coding_tui_run_context_exits_observability_when_unsubscribe_fails() -> None:
    from loushang.coding.ui.run_context import CodingTuiRunContext

    calls: list[str] = []

    class ObservabilityContext:
        def __exit__(self, exc_type, exc, traceback) -> None:
            calls.append("observability.exit")

    def unsubscribe() -> None:
        calls.append("unsubscribe")
        raise RuntimeError("unsubscribe exploded")

    context = CodingTuiRunContext(
        emit=_emit_in_terminal,
        _unsubscribe=unsubscribe,
        _observability_context=ObservabilityContext(),
        _trace=lambda name, **_data: calls.append(name),
    )

    try:
        context.close()
    except RuntimeError as error:
        assert str(error) == "unsubscribe exploded"
    else:
        raise AssertionError("expected unsubscribe failure")

    assert calls == ["tui.end", "unsubscribe", "observability.exit"]


def test_coding_tui_run_context_close_is_idempotent() -> None:
    from loushang.coding.ui.run_context import CodingTuiRunContext

    calls: list[str] = []

    class ObservabilityContext:
        def __exit__(self, exc_type, exc, traceback) -> None:
            calls.append("observability.exit")

    context = CodingTuiRunContext(
        emit=_emit_in_terminal,
        _unsubscribe=lambda: calls.append("unsubscribe"),
        _observability_context=ObservabilityContext(),
        _trace=lambda name, **_data: calls.append(name),
    )

    context.close()
    context.close()

    assert calls == ["tui.end", "unsubscribe", "observability.exit"]


def test_coding_tui_run_context_preserves_legacy_constructor_and_context_field() -> None:
    from loushang.coding.ui.run_context import CodingTuiRunContext

    observability_context = _ObservabilityContext()
    context = CodingTuiRunContext(
        _emit_in_terminal,
        lambda: None,
        observability_context,
        _noop_trace,
        True,
    )

    assert context._observability_context is observability_context
    assert context._closed is True


class _EventRenderer:
    def handle(self, _event: dict[str, object]) -> None:
        pass


class _ObservabilityContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        pass


async def _emit_in_terminal(write_callable: Callable[[], None], *, label: str) -> None:
    del label
    write_callable()


def _noop_trace(name: str, **data: Any) -> None:
    del name, data
    pass
