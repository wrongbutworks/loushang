from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from loushang.coding.ui.event_policy import event_writes_transcript


class EventRenderer(Protocol):
    def handle(self, event: dict[str, Any]) -> None: ...


class TraceFn(Protocol):
    def __call__(self, name: str, **data: Any) -> None: ...


class StableEmit(Protocol):
    def __call__(self, write_callable: Callable[[], None], *, label: str) -> Awaitable[None]: ...


class CodingUiEventStreamHandler:
    def __init__(
        self,
        *,
        renderer: EventRenderer,
        emit: StableEmit,
        trace: TraceFn,
    ) -> None:
        self._renderer = renderer
        self._emit = emit
        self._trace = trace

    async def handle(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "unknown")
        self._trace("event.start", event_type=event_type)
        try:
            if not event_writes_transcript(event):
                self._renderer.handle(event)
                return
            await self._emit(lambda: self._renderer.handle(event), label=f"event:{event_type}")
        finally:
            self._trace("event.end", event_type=event_type)


__all__ = ["CodingUiEventStreamHandler"]
