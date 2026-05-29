from __future__ import annotations

from dataclasses import dataclass

from loushang.agent import AgentMessage


@dataclass(frozen=True)
class CompactionResult:
    summary: str
    first_kept_entry_id: str
    tokens_before: int
    details: object | None = None


@dataclass(frozen=True)
class CompactionStatus:
    is_compacting: bool
    is_branch_summarizing: bool = False
    last_reason: str | None = None
    last_result: CompactionResult | None = None
    last_error: str | None = None
    aborted: bool = False


@dataclass(frozen=True)
class ContextUsageEstimate:
    tokens: int
    usage_tokens: int
    trailing_tokens: int
    last_usage_index: int | None


@dataclass(frozen=True)
class CompactionPlan:
    previous_compaction_id: str | None
    previous_first_kept_entry_id: str | None
    first_kept_entry_id: str
    summarized_entry_ids: tuple[str, ...]
    turn_prefix_entry_ids: tuple[str, ...]
    kept_entry_ids: tuple[str, ...]
    is_split_turn: bool
    tokens_before: int
    keep_recent_tokens: int


@dataclass(frozen=True)
class CompactionPreparation:
    first_kept_entry_id: str
    messages_to_summarize: list[AgentMessage]
    turn_prefix_messages: list[AgentMessage]
    is_split_turn: bool
    tokens_before: int
    previous_summary: str | None = None
    details: object | None = None
    plan: CompactionPlan | None = None


@dataclass(frozen=True)
class BranchSummaryResult:
    summary: str | None = None
    details: object | None = None
    aborted: bool = False
    error: str | None = None


@dataclass(frozen=True)
class BranchSummaryDetails:
    read_files: list[str]
    modified_files: list[str]


@dataclass(frozen=True)
class BranchPreparation:
    messages: list[AgentMessage]
    entry_ids: list[str]
    total_tokens: int


@dataclass(frozen=True)
class CollectEntriesResult:
    entries: list[object]
    common_ancestor_id: str | None
