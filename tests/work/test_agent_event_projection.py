from __future__ import annotations

from datetime import UTC, datetime


def _context(sequence: int = 1):
    from loushang.work import WorkEventProjectionContext

    return WorkEventProjectionContext(
        run_id="run-1",
        session_id="session-1",
        domain="coding",
        operation_id="op-1",
        sequence=sequence,
        created_at=datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        event_id_prefix="event",
        source_event_ref="agent-event-1",
    )


def test_project_agent_start_and_end_events() -> None:
    from loushang.work import project_agent_event_to_work_events

    started = project_agent_event_to_work_events({"type": "agent_start"}, context=_context(1))
    completed = project_agent_event_to_work_events({"type": "agent_end", "messages": []}, context=_context(2))

    assert [event.kind for event in started] == ["WorkRunStarted"]
    assert started[0].event_id == "event-1"
    assert started[0].delivery_hint == "immediate"
    assert started[0].payload == {"source_type": "agent_start"}
    assert started[0].source_event_ref == "agent-event-1"

    assert [event.kind for event in completed] == ["WorkRunCompleted"]
    assert completed[0].event_id == "event-2"
    assert completed[0].delivery_hint == "immediate"
    assert completed[0].payload == {"source_type": "agent_end", "messages": []}


def test_project_message_update_to_coalesced_content_delta() -> None:
    from loushang.work import project_agent_event_to_work_events

    events = project_agent_event_to_work_events(
        {
            "type": "message_update",
            "message": {"role": "assistant"},
            "assistant_message_event": {"type": "text_delta", "text": "hello"},
        },
        context=_context(3),
    )

    assert len(events) == 1
    event = events[0]
    assert event.kind == "ContentDelta"
    assert event.delivery_hint == "coalesce"
    assert event.sequence == 3
    assert event.payload == {
        "source_type": "message_update",
        "message": {"role": "assistant"},
        "assistant_message_event": {"type": "text_delta", "text": "hello"},
    }


def test_project_tool_events_to_tool_call_work_events() -> None:
    from loushang.work import project_agent_event_to_work_events

    started = project_agent_event_to_work_events(
        {
            "type": "tool_execution_start",
            "tool_call_id": "tool-1",
            "tool_name": "bash",
            "args": {"command": "pytest"},
        },
        context=_context(4),
    )
    completed = project_agent_event_to_work_events(
        {
            "type": "tool_execution_end",
            "tool_call_id": "tool-1",
            "tool_name": "bash",
            "result": {"output": "failed"},
            "is_error": True,
            "duration_ms": 50,
        },
        context=_context(5),
    )

    assert started[0].kind == "ToolCallStarted"
    assert started[0].delivery_hint == "coalesce"
    assert started[0].payload["tool_call_id"] == "tool-1"
    assert started[0].payload["tool_name"] == "bash"

    assert completed[0].kind == "ToolCallCompleted"
    assert completed[0].delivery_hint == "immediate"
    assert completed[0].payload["is_error"] is True
    assert completed[0].payload["duration_ms"] == 50


def test_project_tool_policy_and_approval_events_to_audit_work_events() -> None:
    from loushang.work import project_agent_event_to_work_events

    evaluated = project_agent_event_to_work_events(
        {
            "type": "tool_policy_evaluated",
            "tool_call_id": "tool-1",
            "tool_name": "write",
            "policy_disposition": "ask",
            "policy_code": "tool_requires_approval",
            "policy_reason": "Tool write requires approval",
            "approval_required": True,
            "argument_keys": ["content", "path"],
            "path": "/repo/approved.txt",
        },
        context=_context(6),
    )
    requested = project_agent_event_to_work_events(
        {
            "type": "tool_approval_requested",
            "tool_call_id": "tool-1",
            "tool_name": "write",
            "action_id": "approval-1",
            "policy_code": "tool_requires_approval",
            "policy_reason": "Tool write requires approval",
            "argument_keys": ["content", "path"],
            "path": "/repo/approved.txt",
        },
        context=_context(7),
    )
    resolved = project_agent_event_to_work_events(
        {
            "type": "tool_approval_resolved",
            "tool_call_id": "tool-1",
            "tool_name": "write",
            "action_id": "approval-1",
            "approval_decision": "allow",
            "policy_code": "tool_requires_approval",
            "policy_reason": "Tool write requires approval",
        },
        context=_context(8),
    )

    assert [event.kind for event in [*evaluated, *requested, *resolved]] == [
        "ToolPolicyEvaluated",
        "ToolApprovalRequested",
        "ToolApprovalResolved",
    ]
    assert all(event.delivery_hint == "immediate" for event in [*evaluated, *requested, *resolved])
    assert evaluated[0].payload == {
        "source_type": "tool_policy_evaluated",
        "tool_call_id": "tool-1",
        "tool_name": "write",
        "policy_disposition": "ask",
        "policy_code": "tool_requires_approval",
        "policy_reason": "Tool write requires approval",
        "approval_required": True,
        "argument_keys": ["content", "path"],
        "path": "/repo/approved.txt",
    }
    assert requested[0].payload["action_id"] == "approval-1"
    assert resolved[0].payload["approval_decision"] == "allow"


def test_project_queue_update_to_coalesced_queue_metadata_event() -> None:
    from loushang.work import project_agent_event_to_work_events

    events = project_agent_event_to_work_events(
        {"type": "queue_update", "steering": ["wait"], "follow_up": ["then test"]},
        context=_context(6),
    )

    assert len(events) == 1
    assert events[0].kind == "QueueUpdated"
    assert events[0].delivery_hint == "coalesce"
    assert events[0].payload == {
        "source_type": "queue_update",
        "steering": ["wait"],
        "follow_up": ["then test"],
    }
