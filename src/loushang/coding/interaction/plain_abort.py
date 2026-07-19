from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from loushang.coding.interaction.intent import AbortIntent
from loushang.harnesstui.conversation.control import (
    AbortActionHandler,
    InterruptionRenderer,
    RunControl,
    StableEmit,
    TraceFn,
)

Lifecycle = RunControl
Renderer = InterruptionRenderer


class Controller(Protocol):
    async def dispatch(self, intent: AbortIntent) -> Any: ...


class AbortHandler:
    """Adapt Coding's ``AbortIntent`` to shared abort action control."""

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
        # Preserve the historical Coding attributes as adapter seams.
        self._lifecycle = lifecycle
        self._controller = controller
        self._renderer = renderer
        self._emit = emit
        self._session_running = session_running
        self._trace = trace

    async def abort(self) -> None:
        async def dispatch_abort() -> Any:
            return await self._controller.dispatch(AbortIntent())

        handler = AbortActionHandler(
            run_control=self._lifecycle,
            abort_action=dispatch_abort,
            renderer=self._renderer,
            emit=self._emit,
            session_running=self._session_running,
            trace=self._trace,
        )
        await handler.abort()


__all__ = ["AbortHandler"]
