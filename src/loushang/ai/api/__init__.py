from dataclasses import dataclass

from loushang.ai.api.streaming import (
    complete,
    complete_simple,
    complete_structured,
    stream,
    stream_simple,
)
from loushang.ai.errors import AIError, AIErrorCode, AIErrorInfo
from loushang.ai.options import (
    CacheRetention,
    CallOptions,
    ReasoningOptions,
    RetryOptions,
    SimpleCallOptions,
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
    "complete_structured",
    "AgentRuntimeHints",
    "CompressionPolicy",
    "SessionBudget",
    "AIError",
    "AIErrorCode",
    "AIErrorInfo",
    "ThinkingLevel",
    "ThinkingBudgets",
    "CacheRetention",
    "Transport",
    "CallOptions",
    "SimpleCallOptions",
    "ReasoningOptions",
    "RetryOptions",
    "TimeoutOptions",
    "StopReason",
    "TextSignatureV1",
]
