from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from loushang.coding.event.types import AgentSessionEvent
from loushang.harness.events import (
    BranchSummaryCompleted,
    BranchSummaryStarted,
    ContextCompactionCompleted,
    ContextCompactionStarted,
    ConversationMetadataChanged,
    PackageProgressChanged,
    QueueChanged,
    RetryCompleted,
    RetryStarted,
    RuntimeEvent,
    ToolPolicyAuditEvent,
)


def project_runtime_event_to_session_event(
    event: RuntimeEvent[object],
) -> AgentSessionEvent | None:
    """Project a common runtime fact into Coding's presentation contract."""

    payload = event.payload
    if isinstance(payload, Mapping):
        event_type = payload.get("type")
        if isinstance(event_type, str):
            return cast(AgentSessionEvent, payload)
        return None
    if isinstance(payload, QueueChanged):
        return {
            "type": "queue_update",
            "steering": [item.text for item in payload.snapshot.steering],
            "follow_up": [item.text for item in payload.snapshot.follow_up],
        }
    if isinstance(payload, ContextCompactionStarted):
        result: dict[str, object] = {
            "type": "compaction_start",
            "reason": payload.reason,
        }
        if payload.usage is not None:
            result["usage"] = payload.usage
        return cast(AgentSessionEvent, result)
    if isinstance(payload, ContextCompactionCompleted):
        result = {
            "type": "compaction_end",
            "reason": payload.reason,
            "result": payload.result,
            "aborted": payload.aborted,
            "will_retry": payload.will_retry,
        }
        if payload.error_message is not None:
            result["error_message"] = payload.error_message
        if payload.usage_before is not None:
            result["usage_before"] = payload.usage_before
        if payload.usage_after is not None:
            result["usage_after"] = payload.usage_after
        return cast(AgentSessionEvent, result)
    if isinstance(payload, RetryStarted):
        attempt = payload.attempt
        return {
            "type": "auto_retry_start",
            "attempt": attempt.attempt,
            "max_attempts": attempt.max_attempts,
            "delay_ms": attempt.delay_ms,
            "error_message": attempt.error,
        }
    if isinstance(payload, RetryCompleted):
        outcome = payload.outcome
        result = {
            "type": "auto_retry_end",
            "success": outcome.success,
            "attempt": outcome.attempt,
        }
        if not outcome.success and outcome.error is not None:
            result["final_error"] = outcome.error
        return cast(AgentSessionEvent, result)
    if isinstance(payload, BranchSummaryStarted):
        return {
            "type": "branch_summary_start",
            "target_id": payload.target_id,
            "old_leaf_id": payload.old_leaf_id,
            "summarize": payload.summarize,
        }
    if isinstance(payload, BranchSummaryCompleted):
        result = {
            "type": "branch_summary_end",
            "target_id": payload.target_id,
            "old_leaf_id": payload.old_leaf_id,
            "new_leaf_id": payload.new_leaf_id,
            "summary_entry_id": payload.summary_record_id,
            "cancelled": payload.cancelled,
            "aborted": payload.aborted,
        }
        if payload.error_message is not None:
            result["error_message"] = payload.error_message
        return cast(AgentSessionEvent, result)
    if isinstance(payload, ConversationMetadataChanged):
        return {"type": "session_info_changed", "name": payload.name}
    if isinstance(payload, PackageProgressChanged):
        return {
            "type": "package_progress",
            "progress_type": payload.progress_type,
            "action": payload.action,
            "source": payload.source,
            "message": payload.message,
            "target_path": payload.target_path,
        }
    if isinstance(payload, ToolPolicyAuditEvent):
        return cast(
            AgentSessionEvent,
            {"type": payload.event_type, **dict(payload.details)},
        )
    return None


__all__ = ["project_runtime_event_to_session_event"]
