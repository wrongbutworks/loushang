from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from loushang.ai.context import (
    NORMALIZED_CONTEXT_MARKER,
    NormalizationResult,
    NormalizedContext,
    ensure_normalized_context,
    is_normalized_context,
    normalize_context,
    normalize_context_result,
)
from loushang.ai.types import (
    AssistantMessage,
    Context,
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


class _UnknownMessage:
    role = "custom"


class _UnknownPart:
    type = "custom"


@dataclass(frozen=True)
class _UncopyablePayload:
    items: list[dict[str, int]]

    def __deepcopy__(self, memo: object) -> object:
        raise RuntimeError("blocked")


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

    assert normalized["tools"] == (
        Tool(name="read", description="Read a file", parameters={"type": "object"}),
        Tool(name="write", description="Write a file", parameters={"type": "object"}),
    )


def test_normalize_context_rejects_duck_typed_tools() -> None:
    with pytest.raises(TypeError, match="Unsupported tool type"):
        normalize_context({"messages": [], "tools": [_DuckTypedTool()]})


def test_normalize_context_rejects_dict_tools_with_invalid_names() -> None:
    with pytest.raises(TypeError, match="Unsupported tool name type"):
        normalize_context(
            {
                "messages": [],
                "tools": [{"name": "", "description": "bad"}],
            }
        )


def test_normalize_context_rejects_tool_dataclasses_with_invalid_names() -> None:
    with pytest.raises(TypeError, match="Unsupported tool name type"):
        normalize_context(
            {
                "messages": [],
                "tools": [
                    Tool(
                        name="",
                        description="bad",
                        parameters={"type": "object"},
                    )
                ],
            }
        )


def test_normalize_context_rejects_dict_tools_with_non_object_parameters() -> None:
    with pytest.raises(TypeError, match="Unsupported tool parameters type"):
        normalize_context(
            {
                "messages": [],
                "tools": [
                    {
                        "name": "calc",
                        "description": "Calculate values",
                        "parameters": "bad",
                    }
                ],
            }
        )


def test_normalize_context_rejects_tool_dataclasses_with_non_object_parameters() -> None:
    with pytest.raises(TypeError, match="Unsupported tool parameters type"):
        normalize_context(
            {
                "messages": [],
                "tools": [
                    Tool(
                        name="calc",
                        description="Calculate values",
                        parameters="bad",  # type: ignore[arg-type]
                    )
                ],
            }
        )


def test_normalize_context_rejects_context_tools_with_non_object_parameters() -> None:
    with pytest.raises(TypeError, match="Unsupported tool parameters type"):
        normalize_context(
            Context(
                messages=[],
                tools=[
                    Tool(
                        name="calc",
                        description="Calculate values",
                        parameters="bad",  # type: ignore[arg-type]
                    )
                ],
            )
        )


def test_normalize_context_rejects_context_tools_with_invalid_names() -> None:
    with pytest.raises(TypeError, match="Unsupported tool name type"):
        normalize_context(
            Context(
                messages=[],
                tools=[
                    Tool(
                        name="",
                        description="bad",
                        parameters={"type": "object"},
                    )
                ],
            )
        )


def test_normalize_context_rejects_context_dict_tools_with_non_object_parameters() -> None:
    with pytest.raises(TypeError, match="Unsupported tool parameters type"):
        normalize_context(
            Context(
                messages=[],
                tools=[  # type: ignore[list-item]
                    {
                        "name": "calc",
                        "description": "Calculate values",
                        "parameters": "bad",
                    }
                ],
            )
        )


def test_normalize_context_rejects_non_string_system_prompt() -> None:
    with pytest.raises(TypeError, match="Unsupported system_prompt type"):
        normalize_context({"system_prompt": {"text": "system"}, "messages": []})


def test_normalize_context_rejects_unknown_message_objects() -> None:
    with pytest.raises(TypeError, match="Unsupported message type after normalization"):
        normalize_context({"messages": [_UnknownMessage()]})


def test_normalize_context_rejects_unknown_dict_message_roles() -> None:
    with pytest.raises(TypeError, match="Unsupported message role"):
        normalize_context({"messages": [{"role": "custom", "content": "hello"}]})


def test_normalize_context_rejects_unknown_user_content_parts() -> None:
    with pytest.raises(TypeError, match="Unsupported user content part type"):
        normalize_context(
            {"messages": [{"role": "user", "content": [{"type": "audio"}]}]}
        )


def test_normalize_context_rejects_unknown_user_content_part_objects() -> None:
    with pytest.raises(TypeError, match="Unsupported user content part object"):
        normalize_context(
            {"messages": [{"role": "user", "content": [_UnknownPart()]}]}
        )


def test_normalize_context_returns_immutable_normalized_context() -> None:
    normalized = normalize_context({"messages": []})

    assert isinstance(normalized, NormalizedContext)
    assert NORMALIZED_CONTEXT_MARKER not in normalized
    assert is_normalized_context(normalized) is True
    assert normalized.messages == ()
    assert normalized["messages"] == ()
    with pytest.raises(AttributeError):
        setattr(normalized, "system_prompt", "changed")


def test_normalize_context_snapshots_mutable_message_and_tool_inputs() -> None:
    arguments = {"x": 1}
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments=arguments)
        ],
        api="openai-responses",
        provider="openai",
        model="gpt-test",
        response_id=None,
        usage=_usage(),
        stop_reason="toolUse",
        error_message=None,
        timestamp=1.0,
    )
    tool_parameters = {
        "type": "object",
        "properties": {"x": {"type": "number"}},
    }
    tool = Tool(
        name="calc",
        description="Calculate values",
        parameters=tool_parameters,
    )

    normalized = normalize_context(
        {
            "messages": [assistant],
            "tools": [tool],
        }
    )
    assistant.content.append(TextPart(type="text", text="mutated"))
    arguments["x"] = 2
    tool_parameters["properties"]["x"]["type"] = "string"

    snapshot_assistant = normalized.messages[0]
    assert isinstance(snapshot_assistant, AssistantMessage)
    assert snapshot_assistant.content == [
        ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
    ]
    assert normalized.tools == (
        Tool(
            name="calc",
            description="Calculate values",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "number"}},
            },
        ),
    )
    with pytest.raises(TypeError, match="NormalizedContext values are immutable"):
        snapshot_assistant.content.append(TextPart(type="text", text="blocked"))
    snapshot_tool_call = snapshot_assistant.content[0]
    assert isinstance(snapshot_tool_call, ToolCall)
    with pytest.raises(TypeError, match="NormalizedContext values are immutable"):
        snapshot_tool_call.arguments["x"] = 2
    frozen_arguments = snapshot_tool_call.arguments
    with pytest.raises(TypeError, match="NormalizedContext values are immutable"):
        frozen_arguments |= {"y": 3}
    assert normalized.tools is not None
    with pytest.raises(TypeError, match="NormalizedContext values are immutable"):
        normalized.tools[0].parameters["type"] = "string"


def test_normalize_context_rejects_uncopyable_values_without_mutating_input() -> None:
    payload = _UncopyablePayload(items=[{"x": 1}])

    with pytest.raises(TypeError, match="could not be snapshotted"):
        normalize_context({"messages": [], "payload": payload})

    assert type(payload.items) is list
    assert type(payload.items[0]) is dict
    payload.items[0]["x"] = 2
    assert payload.items == [{"x": 2}]


def test_ensure_normalized_context_is_idempotent_for_normalized_context() -> None:
    normalized = normalize_context({"messages": []})

    ensured = ensure_normalized_context(normalized)

    assert ensured is normalized
    assert is_normalized_context(ensured) is True


def test_ensure_normalized_context_does_not_trust_legacy_marker_dict() -> None:
    ensured = ensure_normalized_context(
        {
            NORMALIZED_CONTEXT_MARKER: True,
            "messages": [{"role": "system", "content": "system text"}],
        }
    )

    assert isinstance(ensured, NormalizedContext)
    assert ensured.system_prompt == "system text"
    assert ensured.messages == ()
    assert NORMALIZED_CONTEXT_MARKER not in ensured


def test_normalize_context_result_wraps_normalized_context() -> None:
    result = normalize_context_result({"messages": [], "emit_thinking": True})

    assert isinstance(result, NormalizationResult)
    assert isinstance(result.context, NormalizedContext)
    assert result.context["emit_thinking"] is True
    assert result.diagnostics == ()


def test_normalize_context_reprojects_normalized_context_for_new_model() -> None:
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call:1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
        provider="openai",
        model="gpt-test",
        response_id=None,
        usage=_usage(),
        stop_reason="toolUse",
        error_message=None,
        timestamp=1.0,
    )
    tool_result = ToolResultMessage(
        role="toolResult",
        tool_call_id="call:1",
        tool_name="calc",
        content=[TextPart(type="text", text="1")],
        is_error=False,
        timestamp=2.0,
    )
    first = normalize_context({"messages": [assistant, tool_result]})

    reprojected = normalize_context(
        first,
        model=SimpleNamespace(
            api="anthropic-messages",
            provider_id="anthropic",
            id="claude-test",
        ),
    )

    next_assistant = reprojected.messages[0]
    next_tool_result = reprojected.messages[1]
    assert isinstance(next_assistant, AssistantMessage)
    assert isinstance(next_tool_result, ToolResultMessage)
    assert next_assistant.content[0] == ToolCall(
        type="toolCall",
        id="call_1",
        name="calc",
        arguments={"x": 1},
    )
    assert next_tool_result.tool_call_id == "call_1"


def test_normalize_context_reuses_more_specific_context_for_partial_model_key() -> None:
    normalized = normalize_context(
        {"messages": []},
        model=SimpleNamespace(
            api="openai-responses",
            provider_id="custom",
            id="gpt-test",
        ),
    )

    ensured = ensure_normalized_context(
        normalized,
        model=SimpleNamespace(provider_id="custom", id="gpt-test"),
    )

    assert ensured is normalized


def test_normalize_context_rejects_pairing_mode_change_after_repair() -> None:
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
        provider="openai",
        model="gpt-test",
        response_id=None,
        usage=_usage(),
        stop_reason="toolUse",
        error_message=None,
        timestamp=1.0,
    )
    repaired = normalize_context({"messages": [assistant]}, pairing_mode="repair")

    with pytest.raises(ValueError, match="different pairing_mode"):
        normalize_context(repaired, pairing_mode="strict")


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


def test_normalize_context_canonicalizes_user_dicts_once() -> None:
    normalized = normalize_context(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Look"},
                        {"type": "image", "data": "aW1n", "mimeType": "image/png"},
                    ],
                    "timestamp": 125.0,
                }
            ]
        }
    )

    user = normalized["messages"][0]

    assert isinstance(user, UserMessage)
    assert user.content == [
        TextPart(type="text", text="Look"),
        ImagePart(type="image", data="aW1n", mime_type="image/png"),
    ]
    assert user.timestamp == 125.0


def test_normalize_context_preserves_unknown_usage_cost() -> None:
    normalized = normalize_context(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                    "api": "openai-responses",
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "responseId": "resp_1",
                    "usage": {
                        "input": 1,
                        "output": 2,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "totalTokens": 3,
                    },
                    "stopReason": "stop",
                    "timestamp": 123.0,
                }
            ],
        }
    )

    assistant = normalized["messages"][0]

    assert isinstance(assistant, AssistantMessage)
    assert assistant.usage.cost is None


@pytest.mark.parametrize(
    "cost",
    [
        {},
        {"input": 0.1},
        {
            "input": -0.1,
            "output": 0.2,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
            "total": 0.1,
        },
        {
            "input": float("nan"),
            "output": 0.2,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
            "total": 0.2,
        },
    ],
)
def test_normalize_context_rejects_invalid_usage_cost(
    cost: dict[str, float],
) -> None:
    normalized = normalize_context(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                    "api": "openai-responses",
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "usage": {
                        "input": 1,
                        "output": 2,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "totalTokens": 3,
                        "cost": cost,
                    },
                    "stopReason": "stop",
                    "timestamp": 123.0,
                }
            ],
        }
    )

    assistant = normalized["messages"][0]
    assert isinstance(assistant, AssistantMessage)
    assert assistant.usage.cost is None


def test_normalize_context_canonicalizes_usage_cost_aliases() -> None:
    normalized = normalize_context(
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                    "api": "openai-responses",
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "usage": {
                        "input": 1,
                        "output": 2,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "totalTokens": 3,
                        "cost": {
                            "input": 0.1,
                            "output": 0.2,
                            "cache_read": 0.0,
                            "cache_write": 0.0,
                            "total": 0.3,
                        },
                    },
                    "stopReason": "stop",
                    "timestamp": 123.0,
                }
            ],
        }
    )

    assistant = normalized["messages"][0]

    assert isinstance(assistant, AssistantMessage)
    assert assistant.usage.cost == {
        "input": 0.1,
        "output": 0.2,
        "cacheRead": 0.0,
        "cacheWrite": 0.0,
        "total": 0.3,
    }


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

    assert [getattr(message, "role", None) for message in normalized["messages"]] == [
        "assistant",
        "toolResult",
        "user",
    ]
