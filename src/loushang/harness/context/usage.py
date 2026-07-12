from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextUsageEstimate:
    tokens: int
    usage_tokens: int
    trailing_tokens: int
    last_usage_index: int | None


__all__ = ["ContextUsageEstimate"]
