from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field, replace
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai import CallOptions, ReasoningOptions
from loushang.ai.auth import (
    ApiKeyAuth,
    HeadersAuth,
    NoAuth,
    OAuthBearerAuth,
)
from loushang.ai.context import normalize_context
from loushang.ai.model import ModelRegistry, Provider
from loushang.ai.model.domain import (
    AnthropicMessagesConfig,
    Capabilities,
    Endpoint,
    EndpointTransport,
    Model,
)
from loushang.ai.providers.anthropic import AnthropicProvider
from loushang.ai.types import (
    AssistantMessage,
    ImagePart,
    TextPart,
    ThinkingPart,
    Tool,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from tests.providers._runtime import (
    bound_test_model,
    make_provider_request,
    provider_request_for_test,
    start_test_provider_stream,
)

FINE_GRAINED_TOOLS = "fineGrainedTools"
INTERLEAVED_THINKING = "interleavedThinking"
SEND_SESSION_AFFINITY_HEADERS = "sendSessionAffinityHeaders"
SUPPORTS_CACHE_CONTROL_ON_TOOLS = "supportsCacheControlOnTools"
SUPPORTS_EAGER_TOOL_INPUT_STREAMING = "supportsEagerToolInputStreaming"
SUPPORTS_LONG_CACHE_RETENTION = "supportsLongCacheRetention"


def _registry_with_endpoint(provider_id: str, endpoint: Endpoint) -> ModelRegistry:
    return ModelRegistry.from_providers(
        {
            provider_id: Provider(
                id=provider_id,
                endpoints={endpoint.id: endpoint},
            )
        }
    )


def _normalized_context(model, context, options=None):
    if not isinstance(model, Model) or not model.api:
        model = bound_test_model(
            model,
            api="anthropic-messages",
            options=options,
        )
    pairing_mode = (
        "strict" if getattr(options, "pairing_mode", "strict") == "strict" else "repair"
    )
    return normalize_context(context, model=model, pairing_mode=pairing_mode)


def _invoke_raw_parts(
    provider,
    model,
    context,
    options=None,
    request=None,
    *,
    mode: str = "stream",
):
    normalized_context = _normalized_context(
        request.model if request is not None else model,
        context,
        options,
    )
    provider_request = provider_request_for_test(
        provider,
        model,
        normalized_context,
        options=options,
        request=request,
    )
    if mode != "stream":
        provider_request = replace(provider_request, mode=mode)
    return provider.invoke_raw(provider_request)


async def _stream(provider, model, context, options=None, request=None):
    return start_test_provider_stream(
        provider,
        model,
        _normalized_context(
            request.model if request is not None else model,
            context,
            options,
        ),
        options,
        request=request,
    )


def test_stop_reason_mapping_tool_use():
    # 直接调用内部映射函数，验证 "tool_use" -> "toolUse"
    from loushang.ai.providers.anthropic import _map_stop_reason

    assert _map_stop_reason("tool_use") == "toolUse"
    assert _map_stop_reason("max_tokens") == "length"
    assert _map_stop_reason("end_turn") == "stop"


def test_output_config_injected_for_adaptive_thinking():
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    base = AnthropicProviderBase()
    # 伪模型ID包含 opus-4-6 / opus-4-8 -> 支持自适应思考
    assert base.supports_adaptive_thinking("claude-opus-4-6-latest") is True
    assert base.supports_adaptive_thinking("claude-opus-4-8-latest") is True
    # 映射 effort
    assert base.map_thinking_level_to_effort("high", "claude-opus-4-6") == "high"
    assert base.map_thinking_level_to_effort("xhigh", "claude-opus-4-8") == "xhigh"
    assert base.map_thinking_level_to_effort("xhigh", "claude-opus-4-6") == "max"
    assert base.map_thinking_level_to_effort("max", "claude-opus-4-8") == "max"
    assert base.map_thinking_level_to_effort("future", "claude-opus-4-8") is None


def test_anthropic_provider_sends_opus_48_xhigh_adaptive_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(id="claude-opus-4-8", max_tokens=8192),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    auth=ApiKeyAuth("test-key"),
                    reasoning=ReasoningOptions(effort="xhigh"),
                ),
            )
        )
    )

    payload = _FakeAsyncAnthropic.last_stream_kwargs
    assert payload["thinking"] == {"type": "adaptive"}
    assert payload["output_config"] == {"effort": "xhigh"}


def test_anthropic_provider_complete_mode_maps_non_stream_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(
        monkeypatch,
        [],
        response=SimpleNamespace(
            id="msg_complete",
            content=[
                SimpleNamespace(
                    type="thinking",
                    thinking="plan",
                    signature="sig_thinking",
                ),
                SimpleNamespace(type="redacted_thinking", data="sig_redacted"),
                SimpleNamespace(
                    type="tool_use",
                    id=None,
                    name="calc",
                    input={"x": 1},
                ),
                SimpleNamespace(type="text", text="hello"),
            ],
            stop_reason="refusal",
            usage=SimpleNamespace(input_tokens=3, output_tokens=2),
        ),
    )
    provider = AnthropicProvider()

    parts = asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(auth=ApiKeyAuth("test-key")),
                mode="complete",
            )
        )
    )

    assert _FakeAsyncAnthropic.last_stream_kwargs == {}
    assert _FakeAsyncAnthropic.last_create_kwargs["model"] == "claude-sonnet-4-5"
    assert [part["type"] for part in parts] == [
        "response_start",
        "usage_delta",
        "thinking_delta",
        "thinking_signature_delta",
        "redacted_thinking",
        "tool_call_start",
        "tool_call_args_delta",
        "tool_call_done",
        "text_delta",
        "stop_reason",
        "response_error",
    ]
    assert parts[2] == {"type": "thinking_delta", "text": "plan"}
    assert parts[3] == {
        "type": "thinking_signature_delta",
        "signature": "sig_thinking",
    }
    assert parts[5]["id"] == "tool_call_2"
    assert parts[6]["delta"] == '{"x":1}'
    assert parts[9] == {"type": "stop_reason", "stop_reason": "error"}


def test_fine_grained_tool_beta_uses_typed_transport_kind() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    unsupported = AnthropicMessagesConfig(fine_grained_tools=False)
    assert (
        AnthropicProviderBase.should_inject_fine_grained_tools(
            adapter_config=unsupported,
            headers={"anthropic-beta": "other-beta"},
            transport_kind=None,
        )
        is False
    )
    assert (
        AnthropicProviderBase.should_inject_fine_grained_tools(
            adapter_config=unsupported,
            headers={},
            transport_kind="httpx",
        )
        is False
    )
    assert (
        AnthropicProviderBase.should_inject_fine_grained_tools(
            adapter_config=AnthropicMessagesConfig(),
            headers={},
            transport_kind="httpx",
        )
        is True
    )
    assert (
        AnthropicProviderBase.should_inject_fine_grained_tools(
            adapter_config=AnthropicMessagesConfig(fine_grained_tools=True),
            headers={},
            transport_kind=None,
        )
        is True
    )


def test_anthropic_provider_uses_typed_transport_for_fine_grained_beta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    registry = _registry_with_endpoint(
        "anthropic",
        Endpoint(
            id="anthropic-messages",
            provider="anthropic",
            api="anthropic-messages",
            transport=EndpointTransport(kind="httpx"),
            models={
                "claude-sonnet-4-5": Model(
                    id="claude-sonnet-4-5",
                    provider="anthropic",
                    endpoint="anthropic-messages",
                )
            },
        ),
    )
    model = registry.get_model("anthropic", "anthropic-messages", "claude-sonnet-4-5")
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                model,
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(auth=ApiKeyAuth("test-key")),
            )
        )
    )

    assert (
        "fine-grained-tool-streaming-2025-05-14"
        in _last_anthropic_request_headers()["anthropic-beta"]
    )


def test_anthropic_provider_uses_upstream_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    registry = _registry_with_endpoint(
        "anthropic",
        Endpoint(
            id="anthropic-messages",
            provider="anthropic",
            api="anthropic-messages",
            models={
                "claude-sonnet-4-5_public": Model(
                    id="claude-sonnet-4-5_public",
                    provider="anthropic",
                    endpoint="anthropic-messages",
                    upstream_id="claude-sonnet-4-5",
                )
            },
        ),
    )
    model = registry.get_model(
        "anthropic", "anthropic-messages", "claude-sonnet-4-5_public"
    )
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                model,
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(auth=ApiKeyAuth("test-key")),
            )
        )
    )

    assert _FakeAsyncAnthropic.last_stream_kwargs["model"] == "claude-sonnet-4-5"


def test_assistant_block_to_payload_maps_signed_thinking() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    block = ThinkingPart(
        type="thinking",
        thinking="reasoning text",
        thinking_signature="sig_123",
    )

    assert AnthropicProviderBase.assistant_block_to_anthropic_payload(block) == {
        "type": "thinking",
        "thinking": "reasoning text",
        "signature": "sig_123",
    }


def test_assistant_block_to_payload_downgrades_unsigned_thinking_to_text() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    block = ThinkingPart(
        type="thinking",
        thinking="reasoning text",
        thinking_signature=None,
    )

    assert AnthropicProviderBase.assistant_block_to_anthropic_payload(block) == {
        "type": "text",
        "text": "reasoning text",
    }


def test_assistant_block_to_payload_maps_redacted_thinking() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    block = ThinkingPart(
        type="thinking",
        thinking="[Reasoning redacted]",
        thinking_signature="sig_redacted",
        redacted=True,
    )

    assert AnthropicProviderBase.assistant_block_to_anthropic_payload(block) == {
        "type": "redacted_thinking",
        "data": "sig_redacted",
    }


def test_assistant_block_to_payload_keeps_tool_call_shape() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    block = ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})

    assert AnthropicProviderBase.assistant_block_to_anthropic_payload(block) == {
        "type": "tool_use",
        "id": "call_1",
        "name": "calc",
        "input": {"x": 1},
    }


def test_tool_result_content_to_payload_keeps_plain_text_as_string() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    assert (
        AnthropicProviderBase.tool_result_content_to_anthropic_payload(
            [TextPart(type="text", text="hello"), TextPart(type="text", text="world")]
        )
        == "hello\nworld"
    )


def test_tool_result_content_to_payload_maps_image_only_result() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    assert AnthropicProviderBase.tool_result_content_to_anthropic_payload(
        [ImagePart(type="image", data="aGVsbG8=", mime_type="image/png")]
    ) == [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "aGVsbG8=",
            },
        }
    ]


def test_tool_result_content_to_payload_preserves_mixed_content_order() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    assert AnthropicProviderBase.tool_result_content_to_anthropic_payload(
        [
            TextPart(type="text", text="before"),
            ImagePart(type="image", data="aGVsbG8=", mime_type="image/png"),
            TextPart(type="text", text="after"),
        ]
    ) == [
        {"type": "text", "text": "before"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "aGVsbG8=",
            },
        },
        {"type": "text", "text": "after"},
    ]


def test_anthropic_payload_maps_images_oauth_tools_and_groups_tool_results() -> None:
    from loushang.ai.providers.anthropic import _build_anthropic_message_payloads

    messages, system = _build_anthropic_message_payloads(
        normalize_context(
            {
                "system_prompt": "system",
                "messages": [
                    UserMessage(
                        role="user",
                        content=[
                            ImagePart(
                                type="image",
                                data="aW1hZ2U=",
                                mime_type="image/png",
                            )
                        ],
                        timestamp=0.0,
                    ),
                    AssistantMessage(
                        role="assistant",
                        content=[
                            ImagePart(
                                type="image",
                                data="YXNzaXN0YW50",
                                mime_type="image/jpeg",
                            ),
                            ToolCall(
                                type="toolCall",
                                id="call_1",
                                name="read",
                                arguments={"path": "README.md"},
                            ),
                            ToolCall(
                                type="toolCall",
                                id="call_2",
                                name="write",
                                arguments={},
                            ),
                        ],
                        api="anthropic-messages",
                        provider="anthropic",
                        model="claude",
                        response_id=None,
                        usage=Usage(
                            input=0,
                            output=0,
                            cache_read=0,
                            cache_write=0,
                            total_tokens=0,
                            cost={},
                        ),
                        stop_reason="toolUse",
                        error_message=None,
                        timestamp=0.0,
                    ),
                    ToolResultMessage(
                        role="toolResult",
                        tool_call_id="call_1",
                        tool_name="read",
                        content=[TextPart(type="text", text="first")],
                        is_error=False,
                        timestamp=0.0,
                    ),
                    ToolResultMessage(
                        role="toolResult",
                        tool_call_id="call_2",
                        tool_name="write",
                        content=[TextPart(type="text", text="second")],
                        is_error=True,
                        timestamp=0.0,
                    ),
                ],
            }
        ),
        uses_oauth_protocol=True,
    )

    assert system == [{"type": "text", "text": "system"}]
    assert messages[0] == {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "aW1hZ2U=",
                },
            }
        ],
    }
    assert messages[1]["content"] == [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "YXNzaXN0YW50",
            },
        },
        {
            "type": "tool_use",
            "id": "call_1",
            "name": "Read",
            "input": {"path": "README.md"},
        },
        {
            "type": "tool_use",
            "id": "call_2",
            "name": "Write",
            "input": {},
        },
    ]
    assert messages[2] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "call_1",
                "content": "first",
                "is_error": False,
            },
            {
                "type": "tool_result",
                "tool_use_id": "call_2",
                "content": "second",
                "is_error": True,
            },
        ],
    }


def test_anthropic_internal_summarizers_cover_debug_shapes() -> None:
    from loushang.ai.providers.anthropic import (
        _map_stop_reason,
        _optional_int,
        _summarize_sdk_value,
        _summarize_tool_args_json,
        _tool_input_to_json_delta,
    )

    class Dumpable:
        def model_dump(self, *, exclude_none: bool):
            assert exclude_none is True
            return {"path": "README.md", "content": "hello"}

    class Attrs:
        def __init__(self) -> None:
            self.public = ["x" * 300]
            self._private = "hidden"

    assert _tool_input_to_json_delta("") is None
    assert _tool_input_to_json_delta({}) is None
    assert _tool_input_to_json_delta({"path": "README.md"}) == '{"path":"README.md"}'
    assert _tool_input_to_json_delta(["not-json-object"]) is None

    assert _summarize_tool_args_json("") == {
        "chars": 0,
        "valid_json": False,
        "error": "empty",
    }
    assert _summarize_tool_args_json("[1, 2]") == {
        "chars": 6,
        "valid_json": True,
        "kind": "list",
    }
    repaired = _summarize_tool_args_json('{"path":"README.md","content":"hello"')
    assert repaired["valid_json"] is False
    assert repaired["repair_valid"] is True
    assert repaired["repaired_keys"] == ["path", "content"]
    assert repaired["repaired_path"] == "README.md"
    assert repaired["repaired_content_chars"] == 5

    assert _summarize_sdk_value(Dumpable()) == {
        "path": "README.md",
        "content": "hello",
    }
    assert _summarize_sdk_value(Attrs()) == {"public": ["x" * 160 + "...<300 chars>"]}
    assert _summarize_sdk_value(object()).startswith("<object object at ")

    assert _map_stop_reason("refusal") == "error"
    with pytest.raises(ValueError, match="Unhandled stop reason"):
        _map_stop_reason("new_reason")
    assert _optional_int(True) is None
    assert _optional_int(3) == 3
    assert _optional_int("3") is None


def test_apply_oauth_identity_headers_merges_required_betas() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase
    from loushang.ai.providers.anthropic_oauth_compat import AnthropicOAuthBridge

    headers = AnthropicProviderBase.apply_oauth_identity_headers(
        {
            "ANTHROPIC-BETA": "fine-grained-tool-streaming-2025-05-14",
            "USER-AGENT": "custom-agent",
        }
    )

    assert headers["anthropic-beta"] == (
        "claude-code-20250219,oauth-2025-04-20,fine-grained-tool-streaming-2025-05-14"
    )
    assert headers["USER-AGENT"] == "custom-agent"
    assert headers["x-app"] == AnthropicOAuthBridge.SDK_APP_ID
    assert len([key for key in headers if key.casefold() == "anthropic-beta"]) == 1
    assert len([key for key in headers if key.casefold() == "user-agent"]) == 1


def test_apply_beta_headers_merges_case_insensitively() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    headers = AnthropicProviderBase.apply_beta_headers(
        existing_headers={"ANTHROPIC-BETA": "custom-beta"},
        need_interleaved_beta=True,
        force_fine_grained_tools=False,
    )

    assert set(headers["anthropic-beta"].split(",")) == {
        "custom-beta",
        "interleaved-thinking-2025-05-14",
    }
    assert len([key for key in headers if key.casefold() == "anthropic-beta"]) == 1


def test_oauth_tool_name_roundtrip_prefers_registered_tool_name() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    assert AnthropicProviderBase.to_oauth_tool_name("read") == "Read"
    assert (
        AnthropicProviderBase.from_oauth_tool_name(
            "Read",
            [{"name": "read"}],
        )
        == "read"
    )
    assert (
        AnthropicProviderBase.from_oauth_tool_name(
            "TaskOutput",
            [{"name": "task_output"}],
        )
        == "TaskOutput"
    )


def test_anthropic_provider_oauth_request_uses_sdk_headers_and_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0),
                        {
                            "role": "assistant",
                            "content": [
                                ToolCall(
                                    type="toolCall",
                                    id="call_1",
                                    name="read",
                                    arguments={"path": "README.md"},
                                ),
                            ],
                        },
                    ],
                    "tools": [
                        Tool(
                            name="read",
                            description="Read a file",
                            parameters={"type": "object"},
                        ),
                    ],
                },
                CallOptions(
                    auth=OAuthBearerAuth("opaque-oauth-token"),
                    pairing_mode="repair",
                ),
            )
        )
    )

    headers = _FakeAsyncAnthropic.last_stream_kwargs["extra_headers"]
    assert headers["anthropic-beta"] == (
        "claude-code-20250219,oauth-2025-04-20,fine-grained-tool-streaming-2025-05-14"
    )
    assert headers["user-agent"] == "loushang-ai"
    assert headers["x-app"] == "sdk"

    payload = _FakeAsyncAnthropic.last_stream_kwargs
    assert payload["tools"][0]["name"] == "Read"
    assert payload["messages"][1]["content"][0]["name"] == "Read"


def test_anthropic_provider_oauth_stream_maps_claude_code_tool_name_back_to_registered_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(
        monkeypatch,
        [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(id="resp_1", usage=None),
            ),
            SimpleNamespace(
                type="content_block_start",
                content_block=SimpleNamespace(
                    type="tool_use", id="call_1", name="Read"
                ),
            ),
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(
                    type="input_json_delta", partial_json='{"path":"README.md"}'
                ),
            ),
            SimpleNamespace(type="content_block_stop", index=0),
            SimpleNamespace(type="message_stop"),
        ],
    )
    provider = AnthropicProvider()

    parts = asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                    "tools": [
                        Tool(
                            name="read",
                            description="Read a file",
                            parameters={"type": "object"},
                        ),
                    ],
                },
                CallOptions(auth=OAuthBearerAuth("opaque-oauth-token")),
            )
        )
    )

    tool_start = next(part for part in parts if part["type"] == "tool_call_start")
    assert tool_start["name"] == "read"


def test_anthropic_provider_stream_uses_tool_input_from_content_block_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_input = {
        "path": "tmp/bmi.html",
        "content": "<!doctype html><html><body>BMI</body></html>",
    }
    _fake_anthropic_module(
        monkeypatch,
        [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(id="resp_1", usage=None),
            ),
            SimpleNamespace(
                type="content_block_start",
                content_block=SimpleNamespace(
                    type="tool_use",
                    id="call_1",
                    name="write",
                    input=tool_input,
                ),
            ),
            SimpleNamespace(type="content_block_stop", index=0),
            SimpleNamespace(
                type="content_block_start",
                content_block=SimpleNamespace(type="text"),
            ),
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(type="text_delta", text="done"),
            ),
            SimpleNamespace(type="content_block_stop", index=1),
            SimpleNamespace(type="message_stop"),
        ],
    )
    provider = AnthropicProvider()
    trace_events: list[dict] = []

    parts = asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                    "tools": [
                        Tool(
                            name="write",
                            description="Write a file",
                            parameters={"type": "object"},
                        ),
                    ],
                },
                CallOptions(auth=ApiKeyAuth("test-key"), trace=trace_events.append),
            )
        )
    )

    assert [
        part["delta"] for part in parts if part["type"] == "tool_call_args_delta"
    ] == [json.dumps(tool_input, ensure_ascii=False, separators=(",", ":"))]
    assert len([part for part in parts if part["type"] == "tool_call_done"]) == 1
    tool_start_trace = next(
        event for event in trace_events if event.get("type") == "sdk:tool_start"
    )
    tool_start_data = tool_start_trace["data"]
    assert tool_start_data["input"]["path"] == "tmp/bmi.html"
    assert tool_start_data["input"]["content_chars"] == len(tool_input["content"])


def test_anthropic_provider_stream_keeps_interleaved_tool_blocks_by_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(
        monkeypatch,
        [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(id="resp_1", usage=None),
            ),
            SimpleNamespace(
                type="content_block_start",
                index=0,
                content_block=SimpleNamespace(
                    type="tool_use",
                    id="call_read",
                    name="read",
                ),
            ),
            SimpleNamespace(
                type="content_block_start",
                index=1,
                content_block=SimpleNamespace(
                    type="tool_use",
                    id="call_write",
                    name="write",
                ),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(
                    type="input_json_delta", partial_json='{"path":"README.md"}'
                ),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=1,
                delta=SimpleNamespace(
                    type="input_json_delta", partial_json='{"path":"out.txt"}'
                ),
            ),
            SimpleNamespace(type="content_block_stop", index=0),
            SimpleNamespace(type="content_block_stop", index=1),
            SimpleNamespace(type="message_stop"),
        ],
    )
    provider = AnthropicProvider()

    parts = asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                    "tools": [
                        Tool(
                            name="read",
                            description="Read a file",
                            parameters={"type": "object"},
                        ),
                        Tool(
                            name="write",
                            description="Write a file",
                            parameters={"type": "object"},
                        ),
                    ],
                },
                CallOptions(auth=ApiKeyAuth("test-key")),
            )
        )
    )

    assert [
        (part.get("index"), part.get("id"), part.get("name"))
        for part in parts
        if part["type"] == "tool_call_start"
    ] == [(0, "call_read", "read"), (1, "call_write", "write")]
    assert [
        (part.get("index"), part.get("delta"))
        for part in parts
        if part["type"] == "tool_call_args_delta"
    ] == [(0, '{"path":"README.md"}'), (1, '{"path":"out.txt"}')]
    assert [
        part.get("index") for part in parts if part["type"] == "tool_call_done"
    ] == [0, 1]


def test_anthropic_provider_payload_snapshot_for_mixed_assistant_and_tool_result_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[
                                TextPart(type="text", text="look at this"),
                                ImagePart(
                                    type="image", data="dXNlcg==", mime_type="image/png"
                                ),
                            ],
                            timestamp=0.0,
                        ),
                        {
                            "role": "assistant",
                            "content": [
                                TextPart(type="text", text="working on it"),
                                ThinkingPart(
                                    type="thinking",
                                    thinking="chain of thought",
                                    thinking_signature="sig_assistant",
                                ),
                                ToolCall(
                                    type="toolCall",
                                    id="call_1",
                                    name="calc",
                                    arguments={"x": 1},
                                ),
                            ],
                        },
                        {
                            "role": "toolResult",
                            "tool_call_id": "call_1",
                            "tool_name": "calc",
                            "is_error": False,
                            "content": [
                                TextPart(type="text", text="before"),
                                ImagePart(
                                    type="image", data="aGVsbG8=", mime_type="image/png"
                                ),
                                TextPart(type="text", text="after"),
                            ],
                        },
                    ],
                    "tools": [
                        Tool(
                            name="calc",
                            description="Calculate values",
                            parameters={"type": "object"},
                        ),
                    ],
                },
                CallOptions(auth=ApiKeyAuth("test-key")),
            )
        )
    )

    payload = _FakeAsyncAnthropic.last_stream_kwargs
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look at this"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "dXNlcg==",
                    },
                },
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "working on it"},
                {
                    "type": "thinking",
                    "thinking": "chain of thought",
                    "signature": "sig_assistant",
                },
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "calc",
                    "input": {"x": 1},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_1",
                    "content": [
                        {"type": "text", "text": "before"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "aGVsbG8=",
                            },
                        },
                        {"type": "text", "text": "after"},
                    ],
                    "is_error": False,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        },
    ]


def test_anthropic_provider_respects_explicit_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(
        monkeypatch,
        [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(id="resp_1", usage=None),
            ),
            SimpleNamespace(
                type="message_delta",
                delta=SimpleNamespace(stop_reason="end_turn"),
                usage=None,
            ),
            SimpleNamespace(type="message_stop"),
        ],
    )

    provider = AnthropicProvider()
    stream = asyncio.run(
        _stream(
            provider,
            Model(
                id="claude-test", provider="anthropic", endpoint="anthropic-messages"
            ),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            CallOptions(auth=ApiKeyAuth("test-key"), max_output_tokens=1234),
        )
    )
    asyncio.run(stream.result())

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 1234


def test_anthropic_provider_stream_usage_delta_preserves_missing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(
        monkeypatch,
        [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(
                    id="resp_usage",
                    usage=SimpleNamespace(
                        input_tokens=100,
                        output_tokens=1,
                        cache_read_input_tokens=40,
                        cache_creation_input_tokens=10,
                    ),
                ),
            ),
            SimpleNamespace(
                type="message_delta",
                delta=SimpleNamespace(stop_reason="end_turn"),
                usage=SimpleNamespace(
                    input_tokens=None,
                    output_tokens=20,
                    cache_read_input_tokens=None,
                    cache_creation_input_tokens=None,
                ),
            ),
            SimpleNamespace(type="message_stop"),
        ],
    )
    provider = AnthropicProvider()

    async def _scenario():
        stream = await _stream(
            provider,
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            CallOptions(auth=ApiKeyAuth("test-key")),
        )
        return await stream.result()

    message = asyncio.run(_scenario())

    assert message.usage.input == 100
    assert message.usage.cache_read == 40
    assert message.usage.cache_write == 10
    assert message.usage.output == 20


def test_anthropic_provider_uses_resolved_capability_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()
    request = make_provider_request(
        _Model(max_tokens=8192),
        api="anthropic-messages",
        base_url=None,
        headers={"x-api-key": "test-key"},
        capabilities=Capabilities(max_tokens=2048),
        upstream_model_id="claude-sonnet-4-5",
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(max_tokens=8192),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(auth=ApiKeyAuth("ignored-options-key")),
                request,
            )
        )
    )

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 2048


def test_anthropic_provider_uses_typed_protocol_over_stale_false_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()
    request = make_provider_request(
        _Model(),
        api="anthropic-messages",
        base_url=None,
        headers={"x-api-key": "test-key"},
        adapter_config=AnthropicMessagesConfig(
            session_affinity_headers=True,
            long_cache_retention=True,
            fine_grained_tools=True,
            interleaved_thinking=True,
        ),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[TextPart(type="text", text="hello")],
                            timestamp=0.0,
                        )
                    ]
                },
                CallOptions(
                    auth=ApiKeyAuth("ignored-options-key"),
                    cache_retention="long",
                    cache_key="sess_typed",
                    reasoning=ReasoningOptions(enabled=True),
                ),
                request,
            )
        )
    )

    headers = _last_anthropic_request_headers()
    assert headers["session_id"] == "sess_typed"
    assert headers["x-client-request-id"] == "sess_typed"
    assert headers["x-session-affinity"] == "sess_typed"
    assert "fine-grained-tool-streaming-2025-05-14" in headers["anthropic-beta"]
    assert "interleaved-thinking-2025-05-14" in headers["anthropic-beta"]
    payload = _FakeAsyncAnthropic.last_stream_kwargs
    assert payload["messages"][0]["content"][0]["cache_control"] == {
        "type": "ephemeral",
        "ttl": "1h",
    }


def test_anthropic_provider_uses_typed_protocol_over_stale_true_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()
    request = make_provider_request(
        _Model(),
        api="anthropic-messages",
        base_url=None,
        headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        adapter_config=AnthropicMessagesConfig(
            session_affinity_headers=False,
            long_cache_retention=False,
            fine_grained_tools=False,
            interleaved_thinking=False,
        ),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[TextPart(type="text", text="hello")],
                            timestamp=0.0,
                        )
                    ]
                },
                CallOptions(
                    auth=ApiKeyAuth("ignored-options-key"),
                    cache_retention="long",
                    cache_key="sess_stale",
                    reasoning=ReasoningOptions(enabled=True),
                ),
                request,
            )
        )
    )

    headers = _last_anthropic_request_headers()
    assert headers["X-Api-Key"] == "test-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "anthropic-beta" not in headers
    assert "session_id" not in headers
    assert "x-client-request-id" not in headers
    assert "x-session-affinity" not in headers
    assert "anthropic-beta" not in headers
    assert "session_id" not in headers
    assert "x-client-request-id" not in headers
    assert "x-session-affinity" not in headers
    payload = _FakeAsyncAnthropic.last_stream_kwargs
    assert payload["messages"][0]["content"][0]["cache_control"] == {
        "type": "ephemeral"
    }


def test_anthropic_cache_retention_none_suppresses_cache_key_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()
    request = make_provider_request(
        _Model(),
        api="anthropic-messages",
        headers={"x-api-key": "test-key"},
        adapter_config=AnthropicMessagesConfig(
            session_affinity_headers=True,
            long_cache_retention=True,
        ),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[TextPart(type="text", text="hello")],
                            timestamp=0.0,
                        )
                    ]
                },
                CallOptions(cache_retention="none", cache_key="opaque-cache-key"),
                request=request,
            )
        )
    )

    headers = _last_anthropic_request_headers()
    assert "session_id" not in headers
    assert "x-client-request-id" not in headers
    assert "x-session-affinity" not in headers
    payload = _FakeAsyncAnthropic.last_stream_kwargs
    assert "cache_control" not in payload["messages"][0]["content"][0]


def test_anthropic_provider_clamps_explicit_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(
        monkeypatch,
        [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(id="resp_1", usage=None),
            ),
            SimpleNamespace(type="message_stop"),
        ],
    )

    provider = AnthropicProvider()
    stream = asyncio.run(
        _stream(
            provider,
            Model(
                id="claude-test", provider="anthropic", endpoint="anthropic-messages"
            ),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            CallOptions(auth=ApiKeyAuth("test-key"), max_output_tokens=0),
        )
    )
    asyncio.run(stream.result())

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 1


def test_anthropic_compat_fireworks_uses_session_headers_without_long_cache_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    registry = _registry_with_endpoint(
        "fireworks",
        Endpoint(
            id="anthropic-messages",
            provider="fireworks",
            api="anthropic-messages",
            base_url="https://api.fireworks.ai/inference/v1",
            adapter=AnthropicMessagesConfig(
                session_affinity_headers=True,
                long_cache_retention=False,
            ),
            models={
                "claude-sonnet-4-5": Model(
                    id="claude-sonnet-4-5",
                    provider="fireworks",
                    endpoint="anthropic-messages",
                )
            },
        ),
    )
    model = registry.get_model("fireworks", "anthropic-messages", "claude-sonnet-4-5")
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                model,
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[TextPart(type="text", text="hello")],
                            timestamp=0.0,
                        )
                    ]
                },
                CallOptions(
                    auth=ApiKeyAuth("test-key"),
                    cache_retention="long",
                    cache_key="sess_fireworks",
                ),
            )
        )
    )

    headers = _last_anthropic_request_headers()
    assert headers["session_id"] == "sess_fireworks"
    assert headers["x-client-request-id"] == "sess_fireworks"
    assert headers["x-session-affinity"] == "sess_fireworks"
    payload = _FakeAsyncAnthropic.last_stream_kwargs
    assert payload["messages"][0]["content"][0]["cache_control"] == {
        "type": "ephemeral"
    }


def test_anthropic_provider_uses_model_max_tokens_without_scaling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(max_tokens=8192),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(auth=ApiKeyAuth("test-key")),
            )
        )
    )

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 8192


def test_anthropic_provider_caps_model_max_tokens_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(max_tokens=32768),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(auth=ApiKeyAuth("test-key")),
            )
        )
    )

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 32000


def test_anthropic_payload_groups_consecutive_tool_results_from_same_turn() -> None:
    from loushang.ai.providers.anthropic import _build_anthropic_message_payloads

    messages, _system = _build_anthropic_message_payloads(
        normalize_context(
            {
                "messages": [
                    AssistantMessage(
                        role="assistant",
                        content=[
                            ToolCall(
                                type="toolCall",
                                id="bad_write",
                                name="write",
                                arguments={},
                            ),
                            ToolCall(
                                type="toolCall",
                                id="good_write",
                                name="write",
                                arguments={
                                    "path": "tmp/bmi.html",
                                    "content": "<!doctype html>",
                                },
                            ),
                        ],
                        api="anthropic-messages",
                        provider="anthropic",
                        model="claude-test",
                        response_id=None,
                        usage=Usage(
                            input=0,
                            output=0,
                            cache_read=0,
                            cache_write=0,
                            total_tokens=0,
                            cost=None,
                        ),
                        stop_reason="toolUse",
                        error_message=None,
                        timestamp=0.0,
                    ),
                    ToolResultMessage(
                        role="toolResult",
                        tool_call_id="bad_write",
                        tool_name="write",
                        content=[
                            TextPart(
                                type="text",
                                text='Validation failed for tool "write"',
                            )
                        ],
                        is_error=True,
                        timestamp=0.0,
                    ),
                    ToolResultMessage(
                        role="toolResult",
                        tool_call_id="good_write",
                        tool_name="write",
                        content=[TextPart(type="text", text="Wrote tmp/bmi.html")],
                        is_error=False,
                        timestamp=0.0,
                    ),
                ],
            }
        ),
        uses_oauth_protocol=False,
    )

    assert messages == [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "bad_write", "name": "write", "input": {}},
                {
                    "type": "tool_use",
                    "id": "good_write",
                    "name": "write",
                    "input": {"path": "tmp/bmi.html", "content": "<!doctype html>"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "bad_write",
                    "content": 'Validation failed for tool "write"',
                    "is_error": True,
                },
                {
                    "type": "tool_result",
                    "tool_use_id": "good_write",
                    "content": "Wrote tmp/bmi.html",
                    "is_error": False,
                },
            ],
        },
    ]


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


@pytest.mark.parametrize(
    ("auth", "expected_header", "expected_value"),
    [
        (HeadersAuth({"X-API-KEY": "opaque"}), "X-Api-Key", "opaque"),
        (
            ApiKeyAuth("opaque", header="X-Custom-Auth", prefix="Token "),
            "X-Custom-Auth",
            "Token opaque",
        ),
        (NoAuth(), None, None),
    ],
)
def test_anthropic_forwards_authoritative_auth_headers(
    monkeypatch: pytest.MonkeyPatch,
    auth,
    expected_header: str | None,
    expected_value: str | None,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                AnthropicProvider(),
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(auth=auth),
            )
        )
    )

    headers = _last_anthropic_request_headers()
    assert _FakeAsyncAnthropic.last_init_kwargs["api_key"] == ""
    assert _FakeAsyncAnthropic.last_init_kwargs["auth_token"] == ""
    if expected_header is None:
        assert isinstance(headers["Authorization"], _FakeOmit)
        assert isinstance(headers["X-Api-Key"], _FakeOmit)
    else:
        assert headers[expected_header] == expected_value


@pytest.mark.parametrize(
    ("auth", "uses_oauth_protocol"),
    [
        (OAuthBearerAuth("opaque-token"), True),
        (ApiKeyAuth("sk-ant-oat-looking"), False),
        (
            HeadersAuth({"Authorization": "Bearer sk-ant-oat-looking"}),
            False,
        ),
    ],
)
def test_anthropic_oauth_protocol_is_selected_by_credential_type(
    monkeypatch: pytest.MonkeyPatch,
    auth,
    uses_oauth_protocol: bool,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                AnthropicProvider(),
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(auth=auth),
            )
        )
    )

    headers = _last_anthropic_request_headers()
    assert (headers.get("x-app") == "sdk") is uses_oauth_protocol


def _last_anthropic_request_headers() -> dict[str, object]:
    request_kwargs = (
        _FakeAsyncAnthropic.last_stream_kwargs or _FakeAsyncAnthropic.last_create_kwargs
    )
    headers = request_kwargs.get("extra_headers")
    return headers if isinstance(headers, dict) else {}


def _fake_anthropic_module(
    monkeypatch: pytest.MonkeyPatch,
    events: list[object],
    *,
    response: object | None = None,
) -> None:
    _FakeAsyncAnthropic.events = events
    _FakeAsyncAnthropic.response = response
    _FakeAsyncAnthropic.last_init_kwargs = {}
    _FakeAsyncAnthropic.last_stream_kwargs = {}
    _FakeAsyncAnthropic.last_create_kwargs = {}
    module = ModuleType("anthropic")
    module.AsyncAnthropic = _FakeAsyncAnthropic
    module.Omit = _FakeOmit
    monkeypatch.setitem(sys.modules, "anthropic", module)


class _FakeOmit:
    pass


class _FakeAsyncAnthropic:
    events: list[object] = []
    response: object | None = None
    last_init_kwargs: dict[str, object] = {}
    last_stream_kwargs: dict[str, object] = {}
    last_create_kwargs: dict[str, object] = {}

    def __init__(self, **kwargs) -> None:
        type(self).last_init_kwargs = kwargs
        self.messages = _FakeMessages(type(self))


class _FakeMessages:
    def __init__(self, owner: type[_FakeAsyncAnthropic]) -> None:
        self._owner = owner

    def stream(self, **kwargs):
        self._owner.last_stream_kwargs = kwargs
        return _FakeStreamContext(self._owner.events)

    async def create(self, **kwargs):
        self._owner.last_create_kwargs = kwargs
        return self._owner.response


class _FakeStreamContext:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return _FakeStreamIterator(self._events)


class _FakeStreamIterator:
    def __init__(self, events: list[object]) -> None:
        self._events = iter(events)

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@dataclass(frozen=True)
class _Model:
    id: str = "claude-sonnet-4-5"
    name: str | None = None
    base_url: str | None = None
    reasoning: bool = False
    input: tuple[str, ...] = ("text",)
    cost: object = field(default_factory=dict)
    context_window: int | None = None
    max_tokens: int | None = 4096
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, object] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    provider_id: str = "anthropic"
    endpoint_id: str = "anthropic-messages"
