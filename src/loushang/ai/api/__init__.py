from dataclasses import dataclass

from loushang.ai.api.streaming import complete, complete_simple, stream, stream_simple
from loushang.ai.options import (
    AnthropicOptions,
    CacheRetention,
    CallOptions,
    ModelCallOptions,
    OpenAICompletionsOptions,
    OpenAIResponsesOptions,
    PairingMode,
    ProviderStreamOptions,
    ReasoningOptions,
    RetryOptions,
    SimpleStreamOptions,
    StreamOptions,
    ThinkingBudgets,
    ThinkingLevel,
    TimeoutOptions,
    Transport,
)
from loushang.ai.types import StopReason, TextSignatureV1


@dataclass(frozen=True)
class SessionBudget:
    context_window: int | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class CompressionPolicy:
    enabled: bool = False
    strategy: str | None = None


@dataclass(frozen=True)
class AgentRuntimeHints:
    budget: SessionBudget | None = None
    compression: CompressionPolicy | None = None


__all__ = [
    "stream",
    "complete",
    "stream_simple",
    "complete_simple",
    "AgentRuntimeHints",
    "CompressionPolicy",
    "SessionBudget",
    "ThinkingLevel",
    "ThinkingBudgets",
    "CacheRetention",
    "Transport",
    "CallOptions",
    "ModelCallOptions",
    "ProviderStreamOptions",
    "StreamOptions",
    "SimpleStreamOptions",
    "ReasoningOptions",
    "RetryOptions",
    "TimeoutOptions",
    "AnthropicOptions",
    "OpenAICompletionsOptions",
    "OpenAIResponsesOptions",
    "PairingMode",
    "StopReason",
    "TextSignatureV1",
]
