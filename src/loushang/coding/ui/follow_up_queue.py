from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class Lifecycle(Protocol):
    active: bool
    active_id: int


class Controller(Protocol):
    async def follow_up(self, text: str) -> Any: ...


class Renderer(Protocol):
    def render_status(self, text: str) -> None: ...


class StableEmit(Protocol):
    def __call__(self, write_callable: Callable[[], None], *, label: str) -> Awaitable[None]: ...


class TraceFn(Protocol):
    def __call__(self, name: str, **data: Any) -> None: ...


class FollowUpQueueHandler:
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

    async def queue(self, text: str, *, source: str) -> int | None:
        follow_text = text.strip()
        self._trace(
            "prompt.follow_up.start",
            active_run_id=self._lifecycle.active_id,
            active_run=self._lifecycle.active,
            source=source,
            text_len=len(follow_text),
        )
        if not follow_text:
            self._trace("prompt.follow_up.ignored", reason="empty", source=source)
            return None
        if not self._lifecycle.active:
            await self._emit(
                lambda: self._renderer.render_status("Follow-up is only available while a run is active."),
                label="follow_up:idle",
            )
            return None

        result = await self._controller.follow_up(follow_text)
        self._trace(
            "prompt.follow_up.end",
            error_message=result.error_message,
            exit_code=result.exit_code,
            source=source,
        )
        if result.error_message:
            await self._emit(
                lambda: self._renderer.render_status(result.error_message or "Follow-up is unavailable."),
                label="follow_up:error",
            )
        else:
            await self._emit(
                lambda: self._renderer.render_status("Follow-up queued."),
                label="follow_up:queued",
            )
        return result.exit_code


__all__ = ["FollowUpQueueHandler"]
