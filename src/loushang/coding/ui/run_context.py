from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loushang.coding.ui.event_stream import CodingUiEventStreamHandler
from loushang.coding.ui.startup import CodingTuiStartupSnapshot
from loushang.harnesstui.conversation.run_context import (
    InteractionRunContext,
    StableEmit,
    TraceFn,
    stable_emit_factory,
    subscribe_events,
)


class CodingTuiRunContext(InteractionRunContext):
    """Coding compatibility facade for a neutral interaction run context."""

    def __init__(
        self,
        emit: StableEmit,
        _unsubscribe: Callable[[], None],
        _observability_context: Any,
        _trace: TraceFn,
        _closed: bool = False,
    ) -> None:
        self._observability_context = _observability_context
        super().__init__(
            emit=emit,
            _unsubscribe=_unsubscribe,
            _exit_context=_observability_context,
            _trace=_trace,
            _closed=_closed,
        )


def open_coding_tui_run_context(
    *,
    session: Any,
    snapshot: CodingTuiStartupSnapshot,
    event_renderer: Any,
    interactive: bool,
    log_context_factory: Callable[..., Any],
    trace: TraceFn,
) -> CodingTuiRunContext:
    observability_context = log_context_factory(session_id=snapshot.session_observability_id, cwd=snapshot.cwd, mode="tui")
    observability_context.__enter__()
    try:
        trace(
            "tui.start",
            interactive=interactive,
            model=snapshot.model_label,
            cwd=snapshot.cwd,
            branch=snapshot.branch,
            session=snapshot.session_label,
        )
        stable_emit = stable_emit_factory(trace=trace, interactive=interactive)
        event_stream_handler = CodingUiEventStreamHandler(renderer=event_renderer, emit=stable_emit, trace=trace)
        listener = event_stream_handler.handle if interactive else event_renderer.handle
        unsubscribe = subscribe_session_events(session, listener)
    except Exception:
        observability_context.__exit__(None, None, None)
        raise
    return CodingTuiRunContext(emit=stable_emit, _unsubscribe=unsubscribe, _observability_context=observability_context, _trace=trace)


def subscribe_session_events(session: Any, listener: Any) -> Callable[[], None]:
    """Coding compatibility name for subscribing to Session events."""

    return subscribe_events(session, listener)


__all__ = ["CodingTuiRunContext", "open_coding_tui_run_context", "subscribe_session_events"]
