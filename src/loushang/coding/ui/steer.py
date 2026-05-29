from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class Lifecycle(Protocol):
    active_id: int


class Controller(Protocol):
    async def steer(self, text: str) -> Any: ...


class Renderer(Protocol):
    def render_status(self, text: str) -> None: ...


class StableEmit(Protocol):
    def __call__(self, write_callable: Callable[[], None], *, label: str) -> Awaitable[None]: ...


class TraceFn(Protocol):
    def __call__(self, name: str, **data: Any) -> None: ...


class SteerHandler:
    def __init__(
        self,
        *,
        lifecycle: Lifecycle,
        controller: Controller,
        renderer: Renderer,
        emit: StableEmit,
        trace: TraceFn,
    ) -> None:
        self._lifecycle = lifecycle
        self._controller = controller
        self._renderer = renderer
        self._emit = emit
        self._trace = trace

    async def steer(self, text: str) -> int | None:
        self._trace("prompt.steer.start", active_run_id=self._lifecycle.active_id)
        result = await self._controller.steer(text)
        self._trace("prompt.steer.end", error_message=result.error_message, exit_code=result.exit_code)
        if result.error_message:
            await self._emit(
                lambda: self._renderer.render_status(result.error_message or "Steering is unavailable."),
                label="steer:error",
            )
        return result.exit_code


__all__ = ["SteerHandler"]
