from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from loushang.work.types import DeliveryHint, WorkEvent


@dataclass(frozen=True)
class WorkEventProjectionContext:
    run_id: str
    session_id: str
    domain: str
    operation_id: str
    sequence: int
    created_at: datetime
    event_id_prefix: str = "work-event"
    source_event_ref: str | None = None


def project_agent_event_to_work_events(
    event: Mapping[str, object],
    *,
    context: WorkEventProjectionContext,
) -> list[WorkEvent]:
    source_type = event.get("type")
    if not isinstance(source_type, str):
        raise ValueError("Agent event must include a string type")

    if source_type == "agent_start":
        return [_event(context, kind="WorkRunStarted", delivery_hint="immediate", payload={"source_type": source_type})]
    if source_type == "agent_end":
        return [
            _event(
                context,
                kind="WorkRunCompleted",
                delivery_hint="immediate",
                payload={
                    "source_type": source_type,
                    "messages": event.get("messages", []),
                },
            ),
        ]
    if source_type == "turn_start":
        return [_event(context, kind="TaskStarted", delivery_hint="immediate", payload={"source_type": source_type})]
    if source_type == "turn_end":
        payload = _payload(event, "message", "tool_results")
        return [_event(context, kind="TaskCompleted", delivery_hint="immediate", payload=payload)]
    if source_type in {"message_start", "message_update", "message_end"}:
        payload = _payload(event, "message", "assistant_message_event")
        return [_event(context, kind="ContentDelta", delivery_hint="coalesce", payload=payload)]
    if source_type == "tool_execution_start":
        payload = _payload(event, "tool_call_id", "tool_name", "args")
        return [_event(context, kind="ToolCallStarted", delivery_hint="coalesce", payload=payload)]
    if source_type == "tool_execution_update":
        payload = _payload(event, "tool_call_id", "tool_name", "args", "partial_result")
        return [_event(context, kind="ToolCallProgress", delivery_hint="coalesce", payload=payload)]
    if source_type == "tool_execution_end":
        payload = _payload(event, "tool_call_id", "tool_name", "result", "is_error", "duration_ms")
        delivery_hint: DeliveryHint = "immediate" if event.get("is_error") is True else "coalesce"
        return [_event(context, kind="ToolCallCompleted", delivery_hint=delivery_hint, payload=payload)]
    if source_type == "tool_policy_evaluated":
        payload = _payload(
            event,
            "tool_call_id",
            "tool_name",
            "cwd",
            "policy_disposition",
            "policy_code",
            "policy_reason",
            "approval_required",
            "argument_keys",
            "path",
            "file_path",
            "command",
        )
        return [_event(context, kind="ToolPolicyEvaluated", delivery_hint="immediate", payload=payload)]
    if source_type == "tool_approval_requested":
        payload = _payload(
            event,
            "tool_call_id",
            "tool_name",
            "cwd",
            "action_id",
            "policy_code",
            "policy_reason",
            "argument_keys",
            "path",
            "file_path",
            "command",
        )
        return [_event(context, kind="ToolApprovalRequested", delivery_hint="immediate", payload=payload)]
    if source_type == "tool_approval_resolved":
        payload = _payload(
            event,
            "tool_call_id",
            "tool_name",
            "cwd",
            "action_id",
            "approval_decision",
            "approval_reason",
            "policy_code",
            "policy_reason",
            "argument_keys",
            "path",
            "file_path",
            "command",
        )
        return [_event(context, kind="ToolApprovalResolved", delivery_hint="immediate", payload=payload)]
    if source_type == "queue_update":
        payload = _payload(event, "steering", "follow_up")
        return [_event(context, kind="QueueUpdated", delivery_hint="coalesce", payload=payload)]
    if source_type in {"auto_retry_start", "auto_retry_end"}:
        return [
            _event(
                context,
                kind="RetryDiagnostic",
                delivery_hint="immediate" if event.get("success") is False else "coalesce",
                payload=dict(event),
            ),
        ]
    if source_type in {"compaction_start", "compaction_end", "package_progress"}:
        return [_event(context, kind="MaintenanceProgress", delivery_hint="coalesce", payload=dict(event))]

    return [_event(context, kind="WorkEvent", delivery_hint="coalesce", payload=dict(event))]


def _event(
    context: WorkEventProjectionContext,
    *,
    kind: str,
    delivery_hint: DeliveryHint,
    payload: Mapping[str, object],
) -> WorkEvent:
    return WorkEvent(
        event_id=f"{context.event_id_prefix}-{context.sequence}",
        kind=kind,
        run_id=context.run_id,
        session_id=context.session_id,
        domain=context.domain,
        operation_id=context.operation_id,
        sequence=context.sequence,
        created_at=context.created_at,
        delivery_hint=delivery_hint,
        payload=payload,
        source_event_ref=context.source_event_ref,
    )


def _payload(event: Mapping[str, object], *keys: str) -> dict[str, object]:
    payload: dict[str, object] = {"source_type": event["type"]}
    for key in keys:
        if key in event:
            payload[key] = event[key]
    return payload


__all__ = [
    "WorkEventProjectionContext",
    "project_agent_event_to_work_events",
]
