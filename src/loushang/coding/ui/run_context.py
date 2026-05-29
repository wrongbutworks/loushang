from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from loushang.coding.ui.event_stream import CodingUiEventStreamHandler
from loushang.coding.ui.startup import CodingTuiStartupSnapshot


class TraceFn(Protocol):
    def __call__(self, name: str, **data: Any) -> None: ...


class StableEmit(Protocol):
    def __call__(self, write_callable: Callable[[], None], *, label: str) -> Awaitable[None]: ...


@dataclass
class CodingTuiRunContext:
    emit: StableEmit
    _unsubscribe: Callable[[], None]
    _observability_context: Any
    _trace: TraceFn
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            try:
                self._trace("tui.end")
            finally:
                self._unsubscribe()
        finally:
            self._observability_context.__exit__(None, None, None)


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
        stable_emit = _stable_emit_factory(trace=trace, interactive=interactive)
        event_stream_handler = CodingUiEventStreamHandler(renderer=event_renderer, emit=stable_emit, trace=trace)
        listener = event_stream_handler.handle if interactive else event_renderer.handle
        unsubscribe = subscribe_session_events(session, listener)
    except Exception:
        observability_context.__exit__(None, None, None)
        raise
    return CodingTuiRunContext(emit=stable_emit, _unsubscribe=unsubscribe, _observability_context=observability_context, _trace=trace)


def subscribe_session_events(session: Any, listener: Any) -> Callable[[], None]:
    subscribe = getattr(session, "subscribe", None)
    if callable(subscribe):
        unsubscribe = subscribe(listener)
        if callable(unsubscribe):
            return unsubscribe
    return lambda: None


def _stable_emit_factory(*, trace: TraceFn, interactive: bool) -> StableEmit:
    async def emit(write_callable: Callable[[], None], *, label: str) -> None:
        started = time.monotonic()
        trace("emit.start", label=label, interactive=interactive)
        try:
            write_callable()
        except Exception as error:
            trace(
                "emit.error",
                label=label,
                elapsed_s=time.monotonic() - started,
                error=str(error) or error.__class__.__name__,
            )
            raise
        trace("emit.end", label=label, elapsed_s=time.monotonic() - started)

    return emit


__all__ = ["CodingTuiRunContext", "open_coding_tui_run_context", "subscribe_session_events"]
