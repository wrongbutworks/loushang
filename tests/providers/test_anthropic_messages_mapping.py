from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai.auth.types import OAuthCredentials
from loushang.ai.context import normalize_context
from loushang.ai.model.compat_schema import (
    FINE_GRAINED_TOOLS,
    INTERLEAVED_THINKING,
    SEND_SESSION_AFFINITY_HEADERS,
    SUPPORTS_CACHE_CONTROL_ON_TOOLS,
    SUPPORTS_EAGER_TOOL_INPUT_STREAMING,
    SUPPORTS_LONG_CACHE_RETENTION,
)
from loushang.ai.model.domain import (
    Capabilities,
    Compat,
    Endpoint,
    EndpointProtocolFeatures,
    EndpointTransport,
    Model,
)
from loushang.ai.model.registry import (
    clear_default_model_registry,
    get_default_model_registry,
)
from loushang.ai.options import AnthropicOptions
from loushang.ai.provider import ResolvedRequest
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
from tests.providers._runtime import start_test_provider_stream


def _normalized_context(model, context, options=None):
    pairing_mode = (
        "strict" if getattr(options, "pairing_mode", "strict") == "strict" else "repair"
    )
    return normalize_context(context, model=model, pairing_mode=pairing_mode)


def _stream_raw_parts(provider, model, context, options=None, request=None):
    return provider._stream_raw_parts(
        model,
        _normalized_context(model, context, options),
        options,
        request,
    )


async def _stream(provider, model, context, options=None, request=None):
    return start_test_provider_stream(
        provider,
        model,
        _normalized_context(model, context, options),
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
    # 伪模型ID包含 opus-4-6 -> 支持自适应思考
    assert base.supports_adaptive_thinking("claude-opus-4-6-latest") is True
    # 映射 effort
    assert base.map_thinking_level_to_effort("high", "claude-opus-4-6") == "high"


def test_fine_grained_tool_beta_uses_typed_transport_kind() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase

    unsupported = EndpointProtocolFeatures.from_raw(
        {"tools": {"fineGrained": "unsupported"}}
    )
    assert (
        AnthropicProviderBase.should_inject_fine_grained_tools(
            protocol=unsupported,
            headers={"anthropic-beta": "other-beta"},
            transport_kind=None,
        )
        is False
    )
    assert (
        AnthropicProviderBase.should_inject_fine_grained_tools(
            protocol=unsupported,
            headers={},
            transport_kind="httpx",
        )
        is False
    )
    assert (
        AnthropicProviderBase.should_inject_fine_grained_tools(
            protocol=EndpointProtocolFeatures(),
            headers={},
            transport_kind="httpx",
        )
        is True
    )
    assert (
        AnthropicProviderBase.should_inject_fine_grained_tools(
            protocol=EndpointProtocolFeatures.from_raw(
                {"tools": {"fineGrained": "supported"}}
            ),
            headers={},
            transport_kind=None,
        )
        is True
    )


def test_anthropic_provider_uses_typed_transport_for_fine_grained_beta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    clear_default_model_registry()
    registry = get_default_model_registry()
    registry.register_endpoint(
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
            _stream_raw_parts(
                provider,
                model,
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AnthropicOptions(api_key="test-key"),
            )
        )
    )

    assert (
        "fine-grained-tool-streaming-2025-05-14"
        in _FakeAsyncAnthropic.last_init_kwargs["default_headers"]["anthropic-beta"]
    )


def test_anthropic_provider_uses_upstream_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    clear_default_model_registry()
    registry = get_default_model_registry()
    registry.register_endpoint(
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
            _stream_raw_parts(
                provider,
                model,
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AnthropicOptions(api_key="test-key"),
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


def test_apply_oauth_identity_headers_merges_required_betas() -> None:
    from loushang.ai.providers.anthropic_base import AnthropicProviderBase
    from loushang.ai.providers.anthropic_oauth_compat import AnthropicOAuthCompat

    headers = AnthropicProviderBase.apply_oauth_identity_headers(
        {"anthropic-beta": "fine-grained-tool-streaming-2025-05-14"}
    )

    assert headers["anthropic-beta"] == (
        "claude-code-20250219,oauth-2025-04-20,fine-grained-tool-streaming-2025-05-14"
    )
    assert headers["user-agent"] == AnthropicOAuthCompat.SDK_USER_AGENT
    assert headers["x-app"] == AnthropicOAuthCompat.SDK_APP_ID


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
            _stream_raw_parts(
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
                AnthropicOptions(
                    oauth_credentials={
                        "anthropic": OAuthCredentials(
                            provider="anthropic",
                            access_token="sk-ant-oat-test",
                            expires_at=time.time() + 3600,
                        )
                    },
                    pairing_mode="repair",
                ),
            )
        )
    )

    headers = _FakeAsyncAnthropic.last_init_kwargs["default_headers"]
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
            _stream_raw_parts(
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
                AnthropicOptions(
                    oauth_credentials={
                        "anthropic": OAuthCredentials(
                            provider="anthropic",
                            access_token="sk-ant-oat-test",
                            expires_at=time.time() + 3600,
                        )
                    },
                ),
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
            _stream_raw_parts(
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
                AnthropicOptions(api_key="test-key", trace=trace_events.append),
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
    assert tool_start_trace["input"]["path"] == "tmp/bmi.html"
    assert tool_start_trace["input"]["content_chars"] == len(tool_input["content"])


def test_anthropic_provider_payload_snapshot_for_mixed_assistant_and_tool_result_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
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
                AnthropicOptions(api_key="test-key"),
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
            AnthropicOptions(api_key="test-key", max_tokens=1234),
        )
    )
    asyncio.run(stream.result())

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 1234


def test_anthropic_provider_uses_resolved_capability_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()
    request = ResolvedRequest(
        provider="anthropic",
        endpoint="anthropic-messages",
        api="anthropic-messages",
        base_url=None,
        headers={"x-api-key": "test-key"},
        capabilities=Capabilities(max_tokens=2048),
        upstream_model_id="claude-sonnet-4-5",
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(max_tokens=8192),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AnthropicOptions(api_key="ignored-options-key"),
                request,
            )
        )
    )

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 2048


def test_anthropic_provider_uses_typed_protocol_over_stale_false_compat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()
    request = ResolvedRequest(
        provider="anthropic",
        endpoint="anthropic-messages",
        api="anthropic-messages",
        base_url=None,
        headers={"x-api-key": "test-key"},
        compat={
            SEND_SESSION_AFFINITY_HEADERS: False,
            SUPPORTS_LONG_CACHE_RETENTION: False,
            FINE_GRAINED_TOOLS: False,
            INTERLEAVED_THINKING: False,
        },
        adapter_protocol=EndpointProtocolFeatures.from_raw(
            {
                "reasoning": {"interleaved": "supported"},
                "tools": {"fineGrained": "supported"},
                "cache": {"longRetention": "supported"},
                "session": {"affinityHeaders": "supported"},
            }
        ),
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
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
                AnthropicOptions(
                    api_key="ignored-options-key",
                    cache_retention="long",
                    session_id="sess_typed",
                    thinking_enabled=True,
                ),
                request,
            )
        )
    )

    headers = _FakeAsyncAnthropic.last_init_kwargs["default_headers"]
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


def test_anthropic_provider_uses_typed_protocol_over_stale_true_compat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    provider = AnthropicProvider()
    request = ResolvedRequest(
        provider="anthropic",
        endpoint="anthropic-messages",
        api="anthropic-messages",
        base_url=None,
        headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        compat={
            SEND_SESSION_AFFINITY_HEADERS: True,
            SUPPORTS_LONG_CACHE_RETENTION: True,
            FINE_GRAINED_TOOLS: True,
            INTERLEAVED_THINKING: True,
        },
        adapter_protocol=EndpointProtocolFeatures.from_raw(
            {
                "reasoning": {"interleaved": "unsupported"},
                "tools": {"fineGrained": "unsupported"},
                "cache": {"longRetention": "unsupported"},
                "session": {"affinityHeaders": "unsupported"},
            }
        ),
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
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
                AnthropicOptions(
                    api_key="ignored-options-key",
                    cache_retention="long",
                    session_id="sess_stale",
                    thinking_enabled=True,
                ),
                request,
            )
        )
    )

    headers = _FakeAsyncAnthropic.last_init_kwargs["default_headers"]
    assert headers == {"anthropic-version": "2023-06-01"}
    assert "anthropic-beta" not in headers
    assert "session_id" not in headers
    assert "x-client-request-id" not in headers
    assert "x-session-affinity" not in headers
    payload = _FakeAsyncAnthropic.last_stream_kwargs
    assert payload["messages"][0]["content"][0]["cache_control"] == {
        "type": "ephemeral"
    }


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
            AnthropicOptions(api_key="test-key", max_tokens=0),
        )
    )
    asyncio.run(stream.result())

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 1


def test_anthropic_compat_fireworks_uses_session_headers_without_long_cache_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_anthropic_module(monkeypatch, [SimpleNamespace(type="message_stop")])
    registry = get_default_model_registry()
    registry.register_endpoint(
        "fireworks",
        Endpoint(
            id="anthropic-messages",
            provider="fireworks",
            api="anthropic-messages",
            base_url="https://api.fireworks.ai/inference/v1",
            compat=Compat.from_raw(
                {
                    SEND_SESSION_AFFINITY_HEADERS: True,
                    SUPPORTS_CACHE_CONTROL_ON_TOOLS: False,
                    SUPPORTS_EAGER_TOOL_INPUT_STREAMING: False,
                    SUPPORTS_LONG_CACHE_RETENTION: False,
                }
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
    provider = AnthropicProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(
                    provider_id="fireworks",
                    base_url="https://api.fireworks.ai/inference/v1",
                ),
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[TextPart(type="text", text="hello")],
                            timestamp=0.0,
                        )
                    ]
                },
                AnthropicOptions(
                    api_key="test-key",
                    cache_retention="long",
                    session_id="sess_fireworks",
                ),
            )
        )
    )

    headers = _FakeAsyncAnthropic.last_init_kwargs["default_headers"]
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
            _stream_raw_parts(
                provider,
                _Model(max_tokens=8192),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AnthropicOptions(api_key="test-key"),
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
            _stream_raw_parts(
                provider,
                _Model(max_tokens=32768),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AnthropicOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncAnthropic.last_stream_kwargs["max_tokens"] == 32000


def test_anthropic_payload_groups_consecutive_tool_results_from_same_turn() -> None:
    from loushang.ai.providers.anthropic import _build_anthropic_message_payloads

    messages, _system = _build_anthropic_message_payloads(
        {
            "messages": [
                AssistantMessage(
                    role="assistant",
                    content=[
                        ToolCall(
                            type="toolCall", id="bad_write", name="write", arguments={}
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
                        TextPart(type="text", text='Validation failed for tool "write"')
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
        },
        is_oauth_token=False,
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


def _fake_anthropic_module(
    monkeypatch: pytest.MonkeyPatch, events: list[object]
) -> None:
    _FakeAsyncAnthropic.events = events
    _FakeAsyncAnthropic.last_init_kwargs = {}
    _FakeAsyncAnthropic.last_stream_kwargs = {}
    module = ModuleType("anthropic")
    module.AsyncAnthropic = _FakeAsyncAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", module)


class _FakeAsyncAnthropic:
    events: list[object] = []
    last_init_kwargs: dict[str, object] = {}
    last_stream_kwargs: dict[str, object] = {}

    def __init__(self, **kwargs) -> None:
        type(self).last_init_kwargs = kwargs
        self.messages = _FakeMessages(type(self))


class _FakeMessages:
    def __init__(self, owner: type[_FakeAsyncAnthropic]) -> None:
        self._owner = owner

    def stream(self, **kwargs):
        self._owner.last_stream_kwargs = kwargs
        return _FakeStreamContext(self._owner.events)


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


@pytest.fixture(autouse=True)
def _default_registry() -> None:
    clear_default_model_registry()
    registry = get_default_model_registry()
    registry.register_endpoint(
        "anthropic",
        Endpoint(
            id="anthropic-messages",
            provider="anthropic",
            api="anthropic-messages",
            models={
                "claude-sonnet-4-5": Model(
                    id="claude-sonnet-4-5",
                    provider="anthropic",
                    endpoint="anthropic-messages",
                )
            },
        ),
    )
