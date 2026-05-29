from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

StopReason: TypeAlias = Literal["stop", "length", "toolUse", "error", "aborted"]


@dataclass(slots=True)
class TextContent:
    type: Literal["text"] = "text"
    text: str = ""


@dataclass(slots=True)
class AssistantMessage:
    role: Literal["assistant"] = "assistant"
    content: list[TextContent] | None = None
    stop_reason: StopReason = "stop"
    error_message: str | None = None
    timestamp: int = 0


@dataclass(slots=True)
class StartEvent:
    type: Literal["start"] = "start"
    partial: AssistantMessage | None = None


@dataclass(slots=True)
class TextStartEvent:
    type: Literal["text_start"] = "text_start"
    content_index: int = 0
    partial: AssistantMessage | None = None


@dataclass(slots=True)
class TextDeltaEvent:
    type: Literal["text_delta"] = "text_delta"
    content_index: int = 0
    delta: str = ""
    partial: AssistantMessage | None = None


@dataclass(slots=True)
class TextEndEvent:
    type: Literal["text_end"] = "text_end"
    content_index: int = 0
    content: str = ""
    partial: AssistantMessage | None = None


@dataclass(slots=True)
class DoneEvent:
    type: Literal["done"] = "done"
    reason: Literal["stop", "length", "toolUse"] = "stop"
    message: AssistantMessage | None = None


@dataclass(slots=True)
class ErrorEvent:
    type: Literal["error"] = "error"
    reason: Literal["aborted", "error"] = "error"
    error: AssistantMessage | None = None


AssistantMessageEvent: TypeAlias = (
    StartEvent | TextStartEvent | TextDeltaEvent | TextEndEvent | DoneEvent | ErrorEvent
)

