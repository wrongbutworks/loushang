from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

from loushang.harness.host.retry import RetryAttempt, RetryOutcome
from loushang.harness.host.types import QueueSnapshot

CompactionReason: TypeAlias = Literal["manual", "threshold", "overflow"]
PackageProgressType: TypeAlias = Literal["start", "progress", "complete", "error"]
PackageProgressAction: TypeAlias = Literal[
    "install", "update", "remove", "check", "resolve"
]
ToolPolicyAuditEventType: TypeAlias = Literal[
    "tool_policy_evaluated",
    "tool_approval_requested",
    "tool_approval_resolved",
]


@dataclass(frozen=True)
class QueueChanged:
    snapshot: QueueSnapshot


@dataclass(frozen=True)
class ContextCompactionStarted:
    reason: CompactionReason
    usage: Mapping[str, object] | None = None


@dataclass(frozen=True)
class ContextCompactionCompleted:
    reason: CompactionReason
    result: object | None
    aborted: bool
    will_retry: bool
    error_message: str | None = None
    usage_before: Mapping[str, object] | None = None
    usage_after: Mapping[str, object] | None = None


@dataclass(frozen=True)
class RetryStarted:
    attempt: RetryAttempt


@dataclass(frozen=True)
class RetryCompleted:
    outcome: RetryOutcome


@dataclass(frozen=True)
class BranchSummaryStarted:
    target_id: str
    old_leaf_id: str | None
    summarize: bool


@dataclass(frozen=True)
class BranchSummaryCompleted:
    target_id: str
    old_leaf_id: str | None
    new_leaf_id: str | None
    summary_record_id: str | None
    cancelled: bool
    aborted: bool
    error_message: str | None = None


@dataclass(frozen=True)
class ConversationMetadataChanged:
    name: str | None


@dataclass(frozen=True)
class PackageProgressChanged:
    progress_type: PackageProgressType
    action: PackageProgressAction
    source: str
    message: str | None = None
    target_path: str | None = None


@dataclass(frozen=True)
class ToolPolicyAuditEvent:
    event_type: ToolPolicyAuditEventType
    details: Mapping[str, object]


SessionRuntimeEventPayload: TypeAlias = (
    QueueChanged
    | ContextCompactionStarted
    | ContextCompactionCompleted
    | RetryStarted
    | RetryCompleted
    | BranchSummaryStarted
    | BranchSummaryCompleted
    | ConversationMetadataChanged
    | PackageProgressChanged
    | ToolPolicyAuditEvent
)

_EVENT_KINDS: dict[type[object], str] = {
    QueueChanged: "session.queue_update",
    ContextCompactionStarted: "session.compaction_start",
    ContextCompactionCompleted: "session.compaction_end",
    RetryStarted: "session.auto_retry_start",
    RetryCompleted: "session.auto_retry_end",
    BranchSummaryStarted: "session.branch_summary_start",
    BranchSummaryCompleted: "session.branch_summary_end",
    ConversationMetadataChanged: "session.session_info_changed",
    PackageProgressChanged: "session.package_progress",
}


def session_runtime_event_kind(payload: SessionRuntimeEventPayload) -> str:
    """Return the stable runtime kind for one common Session fact."""

    if isinstance(payload, ToolPolicyAuditEvent):
        return f"session.{payload.event_type}"
    try:
        return _EVENT_KINDS[type(payload)]
    except KeyError as exc:
        raise TypeError(
            f"unsupported Session runtime event payload: {type(payload).__name__}"
        ) from exc


__all__ = [
    "BranchSummaryCompleted",
    "BranchSummaryStarted",
    "CompactionReason",
    "ContextCompactionCompleted",
    "ContextCompactionStarted",
    "ConversationMetadataChanged",
    "PackageProgressAction",
    "PackageProgressChanged",
    "PackageProgressType",
    "QueueChanged",
    "RetryCompleted",
    "RetryStarted",
    "SessionRuntimeEventPayload",
    "ToolPolicyAuditEvent",
    "ToolPolicyAuditEventType",
    "session_runtime_event_kind",
]
