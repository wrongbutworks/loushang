"""Coding-owned event dictionaries projected from the runtime event stream."""

from __future__ import annotations

from typing import Literal, NotRequired, TypeAlias, TypedDict

from loushang.agent import AgentEvent
from loushang.harness.events import (
    CompactionReason,
    PackageProgressAction,
    PackageProgressType,
)


class QueueUpdateEvent(TypedDict):
    type: Literal["queue_update"]
    steering: list[str]
    follow_up: list[str]


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
    progress_type: PackageProgressType
    action: PackageProgressAction
    source: str
    message: str | None
    target_path: str | None


class ToolPolicyAuditSessionEvent(TypedDict):
    type: Literal[
        "tool_policy_evaluated",
        "tool_approval_requested",
        "tool_approval_resolved",
    ]
    tool_name: NotRequired[str]
    tool_call_id: NotRequired[str]
    action_id: NotRequired[str]
    cwd: NotRequired[str]
    policy_disposition: NotRequired[str]
    policy_code: NotRequired[str]
    policy_reason: NotRequired[str]
    approval_required: NotRequired[bool]
    approval_decision: NotRequired[str]
    approval_reason: NotRequired[str]
    argument_keys: NotRequired[list[str]]
    path: NotRequired[str]
    file_path: NotRequired[str]
    command: NotRequired[str | tuple[str, ...]]


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
    | ToolPolicyAuditSessionEvent
)
