from __future__ import annotations

from loushang.coding.message import SessionHeader


def _usage():
    from loushang.ai.types import Usage

    return Usage(
        input=1,
        output=2,
        cache_read=3,
        cache_write=4,
        total_tokens=10,
        cost={
            "input": 0.1,
            "output": 0.2,
            "cacheRead": 0.3,
            "cacheWrite": 0.4,
            "total": 1.0,
        },
    )


def test_serialize_session_header_uses_pi_v3_json_keys() -> None:
    from loushang.coding.message.json_codec import serialize_session_header

    header = SessionHeader(
        type="session",
        version=3,
        id="s1",
        timestamp="2026-05-20T10:00:00.000Z",
        cwd="/tmp/project",
        parent_session="/tmp/parent.jsonl",
    )

    assert serialize_session_header(header) == {
        "type": "session",
        "version": 3,
        "id": "s1",
        "timestamp": "2026-05-20T10:00:00.000Z",
        "cwd": "/tmp/project",
        "parentSession": "/tmp/parent.jsonl",
    }


def test_deserialize_session_header_accepts_pi_v3_json_keys() -> None:
    from loushang.coding.message.json_codec import deserialize_session_header

    assert deserialize_session_header(
        {
            "type": "session",
            "version": 3,
            "id": "s1",
            "timestamp": "2026-05-20T10:00:00.000Z",
            "cwd": "/tmp/project",
            "parentSession": "/tmp/parent.jsonl",
        }
    ) == SessionHeader(
        type="session",
        version=3,
        id="s1",
        timestamp="2026-05-20T10:00:00.000Z",
        cwd="/tmp/project",
        parent_session="/tmp/parent.jsonl",
    )


def test_assistant_message_roundtrip_preserves_response_model_and_signatures() -> None:
    from loushang.ai.types import AssistantMessage, TextPart, ThinkingPart, ToolCall
    from loushang.coding.message.json_codec import (
        deserialize_agent_message,
        serialize_agent_message,
    )

    message = AssistantMessage(
        role="assistant",
        content=[
            ThinkingPart(type="thinking", thinking="reason", thinking_signature="think-sig", redacted=False),
            TextPart(type="text", text="answer", text_signature={"v": 1, "id": "txt", "phase": "final_answer"}),
            ToolCall(type="toolCall", id="tc1", name="read", arguments={"path": "README.md"}, thought_signature="thought"),
        ],
        api="anthropic-messages",
        provider="openrouter",
        model="auto",
        response_id="resp_1",
        usage=_usage(),
        stop_reason="toolUse",
        error_message=None,
        timestamp=123.0,
        response_model="anthropic/claude-sonnet-4.5",
    )

    payload = serialize_agent_message(message)
    assert payload["responseModel"] == "anthropic/claude-sonnet-4.5"

    restored = deserialize_agent_message(payload)
    assert restored == message


def test_tool_result_and_custom_messages_roundtrip_with_images_and_details() -> None:
    from loushang.ai.types import ImagePart, TextPart, ToolResultMessage
    from loushang.coding.message import (
        BashExecutionMessage,
        BranchSummaryMessage,
        CompactionSummaryMessage,
        CustomMessage,
    )
    from loushang.coding.message.json_codec import (
        deserialize_agent_message,
        serialize_agent_message,
    )

    messages = [
        ToolResultMessage(
            role="toolResult",
            tool_call_id="tc1",
            tool_name="read",
            content=[
                TextPart(type="text", text="Read image file [image/png]"),
                ImagePart(type="image", data="aGVsbG8=", mime_type="image/png"),
            ],
            is_error=False,
            timestamp=1.0,
            details={"path": "pixel.png", "isImage": True},
        ),
        BashExecutionMessage(
            role="bashExecution",
            command="npm test",
            output="ok",
            exit_code=0,
            cancelled=False,
            truncated=False,
            full_output_path=None,
            timestamp=2.0,
            exclude_from_context=True,
        ),
        CustomMessage(
            role="custom",
            custom_type="demo.card",
            content=[TextPart(type="text", text="hello")],
            display=True,
            details={"kind": "demo"},
            timestamp=3.0,
        ),
        BranchSummaryMessage(role="branchSummary", summary="branch", from_id="e1", timestamp=4.0),
        CompactionSummaryMessage(role="compactionSummary", summary="compact", tokens_before=99, timestamp=5.0),
    ]

    for message in messages:
        assert deserialize_agent_message(serialize_agent_message(message)) == message
