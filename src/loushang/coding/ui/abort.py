from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from loushang.coding.ui.intent import AbortIntent


class Lifecycle(Protocol):
    active: bool
    active_id: int
    aborted_id: int | None

    def mark_abort_requested(self) -> None: ...


class Controller(Protocol):
    async def dispatch(self, intent: AbortIntent) -> Any: ...


class Renderer(Protocol):
    def render_interruption(self) -> None: ...


class StableEmit(Protocol):
    def __call__(self, write_callable: Callable[[], None], *, label: str) -> Awaitable[None]: ...


class TraceFn(Protocol):
    def __call__(self, name: str, **data: Any) -> None: ...


class AbortHandler:
    def __init__(
        self,
        *,
        lifecycle: Lifecycle,
        controller: Controller,
        renderer: Renderer,
        emit: StableEmit,
        session_running: Callable[[], bool],
        trace: TraceFn,
    ) -> None:
        self._lifecycle = lifecycle
        self._controller = controller
        self._renderer = renderer
        self._emit = emit
        self._session_running = session_running
        self._trace = trace

    async def abort(self) -> None:
        self._trace(
            "abort.start",
            active_run=self._lifecycle.active,
            active_run_id=self._lifecycle.active_id,
            aborted_run_id=self._lifecycle.aborted_id,
            session_running=self._session_running(),
        )
        self._lifecycle.mark_abort_requested()
        await self._emit(self._renderer.render_interruption, label="abort:interruption")
        await self._controller.dispatch(AbortIntent())
        self._trace(
            "abort.end",
            active_run=self._lifecycle.active,
            active_run_id=self._lifecycle.active_id,
            aborted_run_id=self._lifecycle.aborted_id,
            session_running=self._session_running(),
        )


__all__ = ["AbortHandler"]
