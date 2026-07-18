from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CompactionBudget:
    context_window: int
    compact_percent: float
    reserve_tokens: int
    percent_threshold_tokens: int
    reserve_threshold_tokens: int
    threshold_tokens: int
    threshold_reason: Literal["compact_percent", "reserve_tokens"]


def calculate_compaction_budget(
    *,
    context_window: int,
    settings: object | None = None,
    compact_percent: float | None = None,
    reserve_tokens: int | None = None,
) -> CompactionBudget:
    resolved_percent = float(
        compact_percent
        if compact_percent is not None
        else getattr(settings, "compact_percent", 100.0)
    )
    resolved_reserve = int(
        reserve_tokens
        if reserve_tokens is not None
        else getattr(settings, "reserve_tokens", 0)
    )
    normalized_context_window = max(0, int(context_window))
    normalized_percent = max(0.0, min(100.0, resolved_percent))
    normalized_reserve = max(0, resolved_reserve)
    percent_threshold = int(normalized_context_window * normalized_percent / 100)
    reserve_threshold = max(0, normalized_context_window - normalized_reserve)
    if percent_threshold <= reserve_threshold:
        threshold = percent_threshold
        reason: Literal["compact_percent", "reserve_tokens"] = "compact_percent"
    else:
        threshold = reserve_threshold
        reason = "reserve_tokens"
    return CompactionBudget(
        context_window=normalized_context_window,
        compact_percent=normalized_percent,
        reserve_tokens=normalized_reserve,
        percent_threshold_tokens=percent_threshold,
        reserve_threshold_tokens=reserve_threshold,
        threshold_tokens=threshold,
        threshold_reason=reason,
    )


__all__ = ["CompactionBudget", "calculate_compaction_budget"]
