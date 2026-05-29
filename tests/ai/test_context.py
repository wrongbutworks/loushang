from __future__ import annotations

import pytest

from loushang.ai.context import (
    NORMALIZED_CONTEXT_MARKER,
    ensure_normalized_context,
    is_normalized_context,
    normalize_context,
)
from loushang.ai.types import (
    AssistantMessage,
    ImagePart,
    TextPart,
    ThinkingPart,
    Tool,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from loushang.coding.tools import create_write_tool_definition


def _usage() -> object:
    from loushang.ai.types import Usage

    return Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={})


def _write_tool() -> Tool:
    definition = create_write_tool_definition()
    return Tool(name=definition.name, description=definition.description, parameters=definition.parameters)


class _DuckTypedTool:
    name = "calc"
    description = "calculate"
    parameters = {"type": "object"}


def test_normalize_context_accepts_tool_dataclasses_and_dicts() -> None:
    normalized = normalize_context(
        {
            "messages": [],
            "tools": [
                Tool(
                    name="read",
                    description="Read a file",
                    parameters={"type": "object"},
                ),
                {
                    "name": "write",
                    "description": "Write a file",
                    "parameters": {"type": "object"},
                },
            ],
        }
    )

    assert normalized["tools"] == [
        Tool(name="read", description="Read a file", parameters={"type": "object"}),
        Tool(name="write", description="Write a file", parameters={"type": "object"}),
    ]


def test_normalize_context_rejects_duck_typed_tools() -> None:
    with pytest.raises(TypeError, match="Unsupported tool type"):
        normalize_context({"messages": [], "tools": [_DuckTypedTool()]})


def test_normalize_context_marks_normalized_payload() -> None:
    normalized = normalize_context({"messages": []})

    assert normalized[NORMALIZED_CONTEXT_MARKER] is True
    assert is_normalized_context(normalized) is True


def test_ensure_normalized_context_is_idempotent_for_normalized_payload() -> None:
    normalized = normalize_context({"messages": []})

    ensured = ensure_normalized_context(normalized)

    assert ensured == normalized
    assert is_normalized_context(ensured) is True


def test_normalize_context_accepts_pi_style_assistant_and_tool_result_dicts() -> None:
    normalized = normalize_context(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "private reasoning",
                            "thinkingSignature": "thinking-sig",
                        },
                        {
                            "type": "toolCall",
                            "id": "call_1",
                            "name": "read_image",
                            "arguments": {"path": "diagram.png"},
                            "thoughtSignature": "tool-call-sig",
                        },
                    ],
                    "api": "openai-responses",
                    "provider": "github-copilot",
                    "model": "gpt-5",
                    "responseId": "resp_1",
                    "usage": {"input": 1, "output": 2, "cacheRead": 3, "cacheWrite": 4, "totalTokens": 10, "cost": {"usd": 0.01}},
                    "stopReason": "toolUse",
                    "errorMessage": None,
                    "timestamp": 123.0,
                    "responseModel": "gpt-5",
                },
                {
                    "role": "toolResult",
                    "toolCallId": "call_1",
                    "toolName": "read_image",
                    "content": [
                        {"type": "text", "text": "A diagram."},
                        {"type": "image", "data": "aW1hZ2U=", "mimeType": "image/png"},
                    ],
                    "isError": False,
                    "timestamp": 124.0,
                    "details": {"source": "test"},
                },
            ],
        }
    )

    assistant = normalized["messages"][0]
    tool_result = normalized["messages"][1]

    assert len(normalized["messages"]) == 2
    assert isinstance(assistant, AssistantMessage)
    assert assistant.content == [
        ThinkingPart(type="thinking", thinking="private reasoning", thinking_signature="thinking-sig"),
        ToolCall(
            type="toolCall",
            id="call_1",
            name="read_image",
            arguments={"path": "diagram.png"},
            thought_signature="tool-call-sig",
        ),
    ]
    assert assistant.response_id == "resp_1"
    assert assistant.usage.cache_read == 3
    assert assistant.stop_reason == "toolUse"
    assert assistant.response_model == "gpt-5"
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.tool_call_id == "call_1"
    assert tool_result.tool_name == "read_image"
    assert tool_result.content == [
        TextPart(type="text", text="A diagram."),
        ImagePart(type="image", data="aW1hZ2U=", mime_type="image/png"),
    ]
    assert tool_result.details == {"source": "test"}


def test_normalize_context_accepts_string_assistant_dict_content() -> None:
    normalized = normalize_context(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": "Plain assistant text.",
                    "timestamp": 1,
                },
            ],
        }
    )

    assistant = normalized["messages"][0]

    assert isinstance(assistant, AssistantMessage)
    assert assistant.content == [TextPart(type="text", text="Plain assistant text.")]


def test_normalize_context_keeps_malformed_historical_tool_call_recoverable() -> None:
    normalized = normalize_context(
        {
            "messages": [
                AssistantMessage(
                    role="assistant",
                    content=[ToolCall(type="toolCall", id="write-empty", name="write", arguments={})],
                    api="anthropic-messages",
                    provider="moonshot",
                    model="kimi-for-coding",
                    response_id=None,
                    usage=_usage(),
                    stop_reason="toolUse",
                    error_message=None,
                    timestamp=1.0,
                ),
                ToolResultMessage(
                    role="toolResult",
                    tool_call_id="write-empty",
                    tool_name="write",
                    content=[
                        TextPart(
                            type="text",
                            text=(
                                'Validation failed for tool "write":\n'
                                "  - path: is required\n"
                                "  - content: is required"
                            ),
                        )
                    ],
                    is_error=True,
                    timestamp=2.0,
                ),
                UserMessage(role="user", content=[TextPart(type="text", text="你好")], timestamp=3.0),
            ],
            "tools": [_write_tool()],
        }
    )

    assert [getattr(message, "role", None) for message in normalized["messages"]] == ["assistant", "toolResult", "user"]
