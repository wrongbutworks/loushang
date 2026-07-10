from __future__ import annotations

from typing import Any

from loushang.ai.types import AssistantMessage
from loushang.coding.compaction import (
    calculate_context_tokens,
    estimate_context_tokens,
)
from loushang.coding.message import CompactionEntry, SessionMessageEntry
from loushang.coding.session.types import CompactionDecision, ContextUsageSnapshot
from loushang.harness.context.budget import calculate_compaction_budget


def current_context_usage(
    messages: list[Any],
    branch_entries: list[object],
    model: object | None,
) -> tuple[int | None, int | None, float | None]:
    snapshot = build_context_usage_snapshot(messages, branch_entries, model, reserve_tokens=0)
    return snapshot.tokens, snapshot.context_window, snapshot.percent


def build_context_usage_snapshot(
    messages: list[Any],
    branch_entries: list[object],
    model: object | None,
    *,
    reserve_tokens: int,
    compact_percent: float = 100.0,
    keep_recent_tokens: int | None = None,
) -> ContextUsageSnapshot:
    context_window = model_context_window(model)
    if context_window is None:
        return ContextUsageSnapshot(
            tokens=None,
            context_window=None,
            reserve_tokens=reserve_tokens,
            compact_percent=compact_percent,
            keep_recent_tokens=keep_recent_tokens,
            threshold_tokens=None,
            threshold_reason=None,
            percent=None,
            source="unknown",
            last_usage_index=None,
            stale_after_compaction=False,
            compactable=False,
            reason="unknown_context_window",
        )

    budget = calculate_compaction_budget(
        context_window=context_window,
        compact_percent=compact_percent,
        reserve_tokens=reserve_tokens,
    )
    threshold_tokens = budget.threshold_tokens
    latest_compaction = latest_compaction_entry(branch_entries)
    if latest_compaction is not None and not has_post_compaction_usage(branch_entries, latest_compaction):
        return ContextUsageSnapshot(
            tokens=None,
            context_window=context_window,
            reserve_tokens=reserve_tokens,
            compact_percent=budget.compact_percent,
            keep_recent_tokens=keep_recent_tokens,
            percent_threshold_tokens=budget.percent_threshold_tokens,
            reserve_threshold_tokens=budget.reserve_threshold_tokens,
            threshold_tokens=threshold_tokens,
            threshold_reason=budget.threshold_reason,
            percent=None,
            source="unknown",
            last_usage_index=None,
            stale_after_compaction=True,
            compactable=False,
            reason="stale_usage_after_compaction",
        )

    estimate = estimate_context_tokens(messages) if messages else None
    tokens = estimate.tokens if estimate is not None else 0
    last_usage_index = estimate.last_usage_index if estimate is not None else None
    if estimate is None or last_usage_index is None:
        source = "estimated"
    elif estimate.trailing_tokens > 0:
        source = "estimated_from_last_usage"
    else:
        source = "assistant_usage"
    compactable = tokens > threshold_tokens
    return ContextUsageSnapshot(
        tokens=tokens,
        context_window=context_window,
        reserve_tokens=reserve_tokens,
        compact_percent=budget.compact_percent,
        keep_recent_tokens=keep_recent_tokens,
        percent_threshold_tokens=budget.percent_threshold_tokens,
        reserve_threshold_tokens=budget.reserve_threshold_tokens,
        threshold_tokens=threshold_tokens,
        threshold_reason=budget.threshold_reason,
        percent=(tokens / context_window) * 100,
        source=source,
        last_usage_index=last_usage_index,
        stale_after_compaction=False,
        compactable=compactable,
        reason="threshold" if compactable else None,
    )


def build_threshold_compaction_decision(
    messages: list[Any],
    branch_entries: list[object],
    model: object | None,
    *,
    enabled: bool,
    reserve_tokens: int,
    compact_percent: float = 100.0,
    keep_recent_tokens: int | None = None,
) -> CompactionDecision:
    snapshot = build_context_usage_snapshot(
        messages,
        branch_entries,
        model,
        reserve_tokens=reserve_tokens,
        compact_percent=compact_percent,
        keep_recent_tokens=keep_recent_tokens,
    )
    if enabled and snapshot.compactable:
        return CompactionDecision(
            action="threshold",
            usage=snapshot,
            will_retry=False,
            reason=snapshot.reason,
        )
    return CompactionDecision(
        action="none",
        usage=snapshot,
        will_retry=False,
        reason=snapshot.reason,
    )


def model_context_window(model: object | None) -> int | None:
    capabilities = getattr(model, "capabilities", None)
    raw_context_window = getattr(capabilities, "context_window", None)
    if raw_context_window is None:
        raw_context_window = getattr(model, "context_window", None)
    try:
        context_window = int(raw_context_window)
    except (TypeError, ValueError):
        return None
    return context_window if context_window > 0 else None


def latest_compaction_entry(entries: list[object]) -> CompactionEntry | None:
    for entry in reversed(entries):
        if isinstance(entry, CompactionEntry):
            return entry
    return None


def has_post_compaction_usage(entries: list[object], compaction: CompactionEntry) -> bool:
    try:
        compaction_index = entries.index(compaction)
    except ValueError:
        return False
    for entry in reversed(entries[compaction_index + 1 :]):
        if not isinstance(entry, SessionMessageEntry):
            continue
        message = entry.message
        if not isinstance(message, AssistantMessage):
            continue
        if message.stop_reason in {"aborted", "error"}:
            return False
        return calculate_context_tokens(message.usage) > 0
    return False
