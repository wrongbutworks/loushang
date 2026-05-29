from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

PairingMode = Literal["repair", "strict"]


@dataclass(frozen=True)
class StreamOptions:
    signal: object | None = None
    api_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    transport: "Transport | None" = None
    cache_retention: "CacheRetention | None" = None
    session_id: str | None = None
    max_retry_delay_ms: int | None = None
    metadata: dict[str, object] | None = None
    max_tokens: int | None = None
    temperature: float | int | None = None
    timeout: float | int | None = None
    retries: int | None = None
    on_payload: object | None = None
    on_response: object | None = None
    trace: object | None = None
    oauth_credentials: dict[str, object] | None = None
    region: str | None = None
    pairing_mode: PairingMode = "repair"


@dataclass(frozen=True)
class AnthropicOptions(StreamOptions):
    thinking_enabled: bool = False
    thinking_budget_tokens: int | None = None
    effort: str | None = None
    interleaved_thinking: bool = False
    tool_choice: str | dict[str, Any] | None = None


@dataclass(frozen=True)
class OpenAICompletionsOptions(StreamOptions):
    reasoning: str | None = None
    tool_choice: str | dict[str, Any] | None = None


@dataclass(frozen=True)
class OpenAIResponsesOptions(StreamOptions):
    reasoning: str | None = None
    reasoning_summary: str | None = None
    service_tier: str | None = None
    transport: Transport | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class OpenAICodexResponsesOptions(StreamOptions):
    reasoning: str | None = None
    reasoning_summary: str | None = None
    text_verbosity: str | None = None
    transport: Transport | None = None
    session_id: str | None = None


# Explicit option-related types (public)
ThinkingLevel = Literal["minimal", "low", "medium", "high", "xhigh"]


class ThinkingBudgets(TypedDict, total=False):
    minimal: int
    low: int
    medium: int
    high: int


CacheRetention = Literal["none", "short", "long"]


Transport = Literal["sse", "websocket", "auto"]


# Alias to indicate provider-specific extensions on top of StreamOptions.
# In Python, we keep it equal to StreamOptions; providers may downcast to their own options.
ProviderStreamOptions = StreamOptions


@dataclass(frozen=True)
class SimpleStreamOptions(StreamOptions):
    reasoning: "ThinkingLevel | None" = None
    thinking_budgets: "ThinkingBudgets | None" = None
