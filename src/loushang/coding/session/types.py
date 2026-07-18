from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from loushang.coding.commands import CommandSourceInfo, SessionCommandDescriptor
from loushang.coding.types import ModelSelection
from loushang.harness.agent_transcript import (
    TranscriptNavigationResult as TreeNavigationResult,
)
from loushang.harness.host.types import RunState as RunState


@dataclass(frozen=True)
class AgentSessionState:
    run: RunState
    steering: list[str] = field(default_factory=list)
    follow_up: list[str] = field(default_factory=list)
    active_tool_names: list[str] = field(default_factory=list)
    is_compacting: bool = False
    is_retrying: bool = False
    thinking_level: str = "off"
    model_selection: ModelSelection | None = None


@dataclass(frozen=True)
class ContextUsage:
    message_count: int
    assistant_message_count: int
    user_message_count: int
    tool_call_count: int
    tool_result_count: int
    custom_message_count: int
    estimated_context_tokens: int | None
    has_compaction: bool
    branch_depth: int
    leaf_entry_id: str | None
    tokens: int | None = None
    context_window: int | None = None
    percent: float | None = None
    reserve_tokens: int = 0
    compact_percent: float = 100.0
    keep_recent_tokens: int | None = None
    percent_threshold_tokens: int | None = None
    reserve_threshold_tokens: int | None = None
    threshold_tokens: int | None = None
    threshold_reason: Literal["compact_percent", "reserve_tokens"] | None = None
    source: Literal["assistant_usage", "estimated_from_last_usage", "estimated", "unknown"] = "unknown"
    last_usage_index: int | None = None
    stale_after_compaction: bool = False
    compactable: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class ContextUsageSnapshot:
    tokens: int | None
    context_window: int | None
    reserve_tokens: int
    compact_percent: float = 100.0
    keep_recent_tokens: int | None = None
    percent_threshold_tokens: int | None = None
    reserve_threshold_tokens: int | None = None
    threshold_tokens: int | None = None
    threshold_reason: Literal["compact_percent", "reserve_tokens"] | None = None
    percent: float | None = None
    source: Literal["assistant_usage", "estimated_from_last_usage", "estimated", "unknown"] = "unknown"
    last_usage_index: int | None = None
    stale_after_compaction: bool = False
    compactable: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class CompactionDecision:
    action: Literal["none", "threshold", "overflow"]
    usage: ContextUsageSnapshot
    will_retry: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class TokenUsageTotals:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total: int = 0


@dataclass(frozen=True)
class SessionStats:
    session_id: str
    session_name: str | None
    entry_count: int
    message_count: int
    custom_message_count: int
    active_tool_count: int
    is_retrying: bool
    is_compacting: bool
    has_diagnostics: bool
    branch_count: int
    last_model_selection: ModelSelection | None
    context_usage: ContextUsage | None
    tokens: TokenUsageTotals = field(default_factory=TokenUsageTotals)


@dataclass(frozen=True)
class CommandExecutionResult:
    invocation_name: str
    result: object | None = None


__all__ = [
    "AgentSessionState",
    "CompactionDecision",
    "CommandExecutionResult",
    "CommandSourceInfo",
    "ContextUsage",
    "ContextUsageSnapshot",
    "RunState",
    "SessionCommandDescriptor",
    "SessionStats",
    "TokenUsageTotals",
    "TreeNavigationResult",
]
