from __future__ import annotations

from typing import Any, Protocol

from loushang.coding.ui.event_policy import event_writes_transcript
from loushang.harnesstui.conversation.dispatch import (
    EventRenderer as SharedEventRenderer,
)
from loushang.harnesstui.conversation.dispatch import (
    StableEmit,
    StableEventStreamHandler,
    TraceFn,
)


class EventRenderer(SharedEventRenderer[dict[str, Any]], Protocol):
    """Coding-compatible raw event rendering port."""


class CodingUiEventStreamHandler(StableEventStreamHandler[dict[str, Any]]):
    """Adapt Coding raw-event policy to neutral stable event delivery."""

    def __init__(
        self,
        *,
        renderer: EventRenderer,
        emit: StableEmit,
        trace: TraceFn,
    ) -> None:
        super().__init__(
            renderer=renderer,
            emit=emit,
            writes_stably=event_writes_transcript,
            event_type=_coding_event_type,
            trace=trace,
        )


def _coding_event_type(event: dict[str, Any]) -> str:
    return str(event.get("type") or "unknown")


__all__ = ["CodingUiEventStreamHandler"]
