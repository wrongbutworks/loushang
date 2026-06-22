from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loushang.ai.options import CallOptions, Transport


@dataclass(frozen=True, slots=True)
class AnthropicOptions(CallOptions):
    """Deprecated provider-specific extension; prefer CallOptions."""

    thinking_enabled: bool = False
    thinking_budget_tokens: int | None = None
    effort: str | None = None
    interleaved_thinking: bool = False
    tool_choice: str | dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OpenAICompletionsOptions(CallOptions):
    """Deprecated provider-specific extension; prefer CallOptions."""

    reasoning: str | None = None
    tool_choice: str | dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OpenAIResponsesOptions(CallOptions):
    """Deprecated provider-specific extension; prefer CallOptions."""

    reasoning: str | None = None
    reasoning_summary: str | None = None
    service_tier: str | None = None
    transport: Transport | None = None
    session_id: str | None = None


__all__ = [
    "AnthropicOptions",
    "OpenAICompletionsOptions",
    "OpenAIResponsesOptions",
]
