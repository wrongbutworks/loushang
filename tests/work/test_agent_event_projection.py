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

    started = project_agent_event_to_work_events(
        {"type": "agent_start"}, context=_context(1)
    )
    completed = project_agent_event_to_work_events(
        {"type": "agent_end", "messages": []}, context=_context(2)
    )

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


def test_project_messages_with_existing_ai_codecs() -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage
    from loushang.work import project_agent_event_to_work_events

    assistant = AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text="hello")],
        api="responses",
        provider="example",
        model="example-1",
        response_id="response-1",
        usage=Usage(
            input=1,
            output=2,
            cache_read=0,
            cache_write=0,
            total_tokens=3,
            cost=None,
        ),
        stop_reason="stop",
        error_message=None,
        timestamp=1.0,
    )

    message_end = project_agent_event_to_work_events(
        {"type": "message_end", "message": assistant},
        context=_context(3),
    )[0]
    message_update = project_agent_event_to_work_events(
        {
            "type": "message_update",
            "message": assistant,
            "assistant_message_event": {
                "type": "text_delta",
                "content_index": 0,
                "delta": "hello",
                "partial": assistant,
            },
        },
        context=_context(4),
    )[0]

    assert message_end.payload["message"] == {
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "hello",
                "textSignature": None,
            }
        ],
        "api": "responses",
        "provider": "example",
        "model": "example-1",
        "responseId": "response-1",
        "usage": {
            "input": 1,
            "output": 2,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 3,
            "cost": None,
        },
        "stopReason": "stop",
        "errorMessage": None,
        "timestamp": 1.0,
    }
    assert message_update.payload["assistant_message_event"] == {
        "type": "text_delta",
        "partial": message_end.payload["message"],
        "contentIndex": 0,
        "delta": "hello",
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


def test_project_tool_update_and_end_use_agent_event_projection() -> None:
    from dataclasses import dataclass
    from pathlib import Path

    from loushang.agent import AgentToolResult, FunctionalToolOutputProjector
    from loushang.ai.types import TextPart
    from loushang.work import project_agent_event_to_work_events

    @dataclass(frozen=True)
    class RichDetails:
        path: Path

    def result(text: str) -> AgentToolResult[RichDetails]:
        return AgentToolResult(
            content=[TextPart(type="text", text=text)],
            details=RichDetails(path=Path("notes.txt")),
            projector=FunctionalToolOutputProjector(
                transcript=lambda details: {
                    "path": str(details.path),
                    "surface": "transcript",
                },
                event=lambda details: {
                    "path": str(details.path),
                    "surface": "event",
                },
            ),
        )

    progress = project_agent_event_to_work_events(
        {
            "type": "tool_execution_update",
            "tool_call_id": "tool-1",
            "tool_name": "read",
            "args": {"path": "notes.txt"},
            "partial_result": result("partial"),
        },
        context=_context(5),
    )[0]
    completed = project_agent_event_to_work_events(
        {
            "type": "tool_execution_end",
            "tool_call_id": "tool-1",
            "tool_name": "read",
            "result": result("complete"),
            "is_error": False,
        },
        context=_context(6),
    )[0]

    assert progress.payload["partial_result"] == {
        "content": [
            {
                "type": "text",
                "text": "partial",
                "textSignature": None,
            }
        ],
        "details": {"path": "notes.txt", "surface": "event"},
        "terminate": False,
    }
    assert completed.payload["result"] == {
        "content": [
            {
                "type": "text",
                "text": "complete",
                "textSignature": None,
            }
        ],
        "details": {"path": "notes.txt", "surface": "event"},
        "terminate": False,
    }


def test_work_projection_rejects_malformed_tool_result_content() -> None:
    import pytest

    from loushang.agent import AgentToolResult, ToolOutputProjectionError
    from loushang.ai.types import TextPart
    from loushang.work import project_agent_event_to_work_events

    result = AgentToolResult(
        content=[TextPart(type="image", text="oops")],  # type: ignore[arg-type]
        details={},
    )

    with pytest.raises(ToolOutputProjectionError) as exc_info:
        project_agent_event_to_work_events(
            {
                "type": "tool_execution_update",
                "tool_call_id": "tool-1",
                "tool_name": "read",
                "partial_result": result,
            },
            context=_context(5),
        )
    assert exc_info.value.target == "event"
    assert exc_info.value.path == "tool_output.content[0].type"


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
    assert all(
        event.delivery_hint == "immediate"
        for event in [*evaluated, *requested, *resolved]
    )
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


def test_work_event_bridge_rejects_non_json_payloads() -> None:
    from pathlib import Path

    import pytest

    from loushang.protocol import JsonValueError
    from loushang.work import project_agent_event_to_work_events

    cases = (
        (
            {
                "type": "queue_update",
                "steering": [Path("wait")],
                "follow_up": [],
            },
            "work_event.payload.steering[0]",
        ),
        (
            {
                "type": "tool_policy_evaluated",
                "tool_call_id": "call-1",
                "tool_name": "read",
                "path": Path("notes.txt"),
            },
            "work_event.payload.path",
        ),
        (
            {"type": "product_event", "unsafe": Path("notes.txt")},
            "work_event.payload.unsafe",
        ),
    )

    for source_event, expected_path in cases:
        with pytest.raises(JsonValueError) as exc_info:
            project_agent_event_to_work_events(source_event, context=_context())
        assert exc_info.value.path == expected_path


def test_work_event_bridge_snapshots_source_payloads() -> None:
    from loushang.work import project_agent_event_to_work_events

    steering = ["first"]
    source_event = {
        "type": "queue_update",
        "steering": steering,
        "follow_up": [],
    }

    projected = project_agent_event_to_work_events(source_event, context=_context())[0]
    steering.append("later")

    assert projected.payload["steering"] == ["first"]


def test_work_event_bridge_accepts_product_message_serializer() -> None:
    from dataclasses import dataclass, replace

    from loushang.agent import CustomAgentMessage
    from loushang.work import project_agent_event_to_work_events

    @dataclass(frozen=True)
    class ProductMessage(CustomAgentMessage):
        role: str
        text: str

    message = ProductMessage(role="product", text="hello")
    context = replace(
        _context(),
        message_serializer=lambda value: {
            "role": value.role,
            "text": value.text,
        },
    )

    projected = project_agent_event_to_work_events(
        {"type": "message_end", "message": message},
        context=context,
    )[0]

    assert projected.payload["message"] == {
        "role": "product",
        "text": "hello",
    }
