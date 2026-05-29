from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

StopReason = Literal["stop", "length", "toolUse", "error", "aborted"]


@dataclass(slots=True)
class Model:
    id: str
    name: str
    api: str
    provider: str
    base_url: str
    reasoning: bool
    input: list[str]
    context_window: int
    max_tokens: int
    cost: dict[str, int]
    headers: dict[str, str] | None = None
    compat: dict[str, Any] | None = None


@dataclass(slots=True)
class Context:
    system_prompt: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class StreamOptions:
    temperature: float | None = None
    max_tokens: int | None = None
    signal: Any = None
    api_key: str | None = None
    transport: str | None = None
    cache_retention: str | None = None
    session_id: str | None = None
    on_payload: Any = None
    headers: dict[str, str] | None = None
    max_retry_delay_ms: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class SimpleStreamOptions(StreamOptions):
    reasoning: str | None = None
    thinking_budgets: dict[str, int] | None = None


@dataclass(slots=True)
class AssistantMessageEvent:
    type: Literal["start", "text_delta", "done", "error"]
    text: str | None = None
    reason: str | None = None
    message: str | None = None


@dataclass(slots=True)
class TextContent:
    type: Literal["text"] = "text"
    text: str = ""


@dataclass(slots=True)
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    cost: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class AssistantMessage:
    role: Literal["assistant"] = "assistant"
    content: list[TextContent] = field(default_factory=list)
    api: str = ""
    provider: str = ""
    model: str = ""
    response_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    stop_reason: StopReason = "stop"
    error_message: str | None = None
    timestamp: float = 0.0

