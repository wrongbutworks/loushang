from __future__ import annotations

from typing import Literal, NotRequired, TypeAlias, TypedDict

from loushang.agent import AgentEvent


class QueueUpdateEvent(TypedDict):
    type: Literal["queue_update"]
    steering: list[str]
    follow_up: list[str]


CompactionReason: TypeAlias = Literal["manual", "threshold", "overflow"]


class CompactionStartEvent(TypedDict):
    type: Literal["compaction_start"]
    reason: CompactionReason
    usage: NotRequired[object]


class CompactionEndEvent(TypedDict):
    type: Literal["compaction_end"]
    reason: CompactionReason
    result: object | None
    aborted: bool
    will_retry: bool
    error_message: NotRequired[str]
    usage_before: NotRequired[object]
    usage_after: NotRequired[object]


class AutoRetryStartEvent(TypedDict):
    type: Literal["auto_retry_start"]
    attempt: int
    max_attempts: int
    delay_ms: int
    error_message: str


class AutoRetryEndEvent(TypedDict):
    type: Literal["auto_retry_end"]
    success: bool
    attempt: int
    final_error: NotRequired[str]


class BranchSummaryStartEvent(TypedDict):
    type: Literal["branch_summary_start"]
    target_id: str
    old_leaf_id: str | None
    summarize: bool


class BranchSummaryEndEvent(TypedDict):
    type: Literal["branch_summary_end"]
    target_id: str
    old_leaf_id: str | None
    new_leaf_id: str | None
    summary_entry_id: str | None
    cancelled: bool
    aborted: bool
    error_message: NotRequired[str]


class SessionInfoChangedEvent(TypedDict):
    type: Literal["session_info_changed"]
    name: str | None


class PackageProgressSessionEvent(TypedDict):
    type: Literal["package_progress"]
    progress_type: Literal["start", "progress", "complete", "error"]
    action: Literal["install", "update", "remove", "check", "resolve"]
    source: str
    message: str | None
    target_path: str | None


AgentSessionEvent: TypeAlias = (
    AgentEvent
    | QueueUpdateEvent
    | CompactionStartEvent
    | CompactionEndEvent
    | AutoRetryStartEvent
    | AutoRetryEndEvent
    | BranchSummaryStartEvent
    | BranchSummaryEndEvent
    | SessionInfoChangedEvent
    | PackageProgressSessionEvent
)
