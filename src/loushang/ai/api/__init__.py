from dataclasses import dataclass

from loushang.ai.api.streaming import (
    complete,
    complete_structured,
    stream,
)
from loushang.ai.errors import AIError, AIErrorCode, AIErrorInfo
from loushang.ai.options import (
    CacheRetention,
    CallOptions,
    ReasoningOptions,
    RetryOptions,
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
    "complete_structured",
    "AgentRuntimeHints",
    "CompressionPolicy",
    "SessionBudget",
    "AIError",
    "AIErrorCode",
    "AIErrorInfo",
    "ThinkingLevel",
    "CacheRetention",
    "Transport",
    "CallOptions",
    "ReasoningOptions",
    "RetryOptions",
    "TimeoutOptions",
    "StopReason",
    "TextSignatureV1",
]
