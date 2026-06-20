from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai import get_model
from loushang.ai.model import Capabilities, Model
from loushang.ai.model.compat_schema import resolve_openai_completions_compat
from loushang.ai.model.domain import (
    Endpoint,
    EndpointRouting,
    EndpointTransport,
    EndpointWireDialect,
)
from loushang.ai.model.registry import (
    clear_default_model_registry,
    get_default_model_registry,
)
from loushang.ai.options import OpenAICompletionsOptions
from loushang.ai.provider import ResolvedRequest
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
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


def test_openai_completions_payload_maps_user_image_assistant_toolcall_and_tool_result_mixed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, compat={}, reasoning_effort=None)
    provider = OpenAICompletionsProvider()

    assistant = AssistantMessage(
        role="assistant",
        content=[
            TextPart(type="text", text="working"),
            ThinkingPart(
                type="thinking", thinking="plan", thinking_signature="reasoning_content"
            ),
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1}),
        ],
        api="openai-completions",
        provider="openai",
        model="gpt-test",
        response_id="resp_1",
        usage=Usage(
            input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
        ),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )
    tool_result = ToolResultMessage(
        role="toolResult",
        tool_call_id="call_1",
        tool_name="calc",
        content=[
            TextPart(type="text", text="before"),
            ImagePart(type="image", data="aGVsbG8=", mime_type="image/png"),
            TextPart(type="text", text="after"),
        ],
        is_error=False,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(),
                {
                    "system_prompt": "You are helpful.",
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[
                                TextPart(type="text", text="look"),
                                ImagePart(
                                    type="image", data="dXNlcg==", mime_type="image/png"
                                ),
                            ],
                            timestamp=0.0,
                        ),
                        assistant,
                        tool_result,
                    ],
                    "tools": [
                        Tool(
                            name="calc",
                            description="Calculate values",
                            parameters={"type": "object"},
                        ),
                    ],
                },
                OpenAICompletionsOptions(api_key="test-key", tool_choice="required"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["messages"] == [
        {"role": "system", "content": "You are helpful."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,dXNlcg=="},
                },
            ],
        },
        {
            "role": "assistant",
            "content": "working",
            "reasoning_content": "plan",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "calc", "arguments": '{"x": 1}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "before\nafter",
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Attached image(s) from tool result:"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,aGVsbG8="},
                },
            ],
        },
    ]
    assert _FakeAsyncOpenAI.last_create_kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "calc",
                "description": "Calculate values",
                "parameters": {"type": "object"},
                "strict": False,
            },
        }
    ]
    assert _FakeAsyncOpenAI.last_create_kwargs["tool_choice"] == "required"


def test_openai_completions_payload_uses_resolved_capabilities_for_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        reasoning_effort=None,
        capabilities=Capabilities(input=("text", "image")),
    )
    provider = OpenAICompletionsProvider()
    tool_result = ToolResultMessage(
        role="toolResult",
        tool_call_id="call_1",
        tool_name="read",
        content=[ImagePart(type="image", data="dG9vbA==", mime_type="image/png")],
        is_error=False,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(input=("text",)),
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[
                                TextPart(type="text", text="look"),
                                ImagePart(
                                    type="image",
                                    data="dXNlcg==",
                                    mime_type="image/png",
                                ),
                            ],
                            timestamp=0.0,
                        ),
                        tool_result,
                    ],
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,dXNlcg=="},
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "(see attached image)",
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Attached image(s) from tool result:"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,dG9vbA=="},
                },
            ],
        },
    ]


def test_openai_completions_uses_upstream_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        upstream_model_id="openai/gpt-oss-120b:free",
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(id="openai/gpt-oss-120b_free"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["model"] == "openai/gpt-oss-120b:free"


def test_openai_completions_caps_model_max_tokens_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={"maxTokensField": "max_tokens"},
        reasoning_effort=None,
        max_tokens=None,
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(max_tokens=32768),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_tokens"] == 32000


def test_openai_completions_uses_resolved_capability_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={"maxTokensField": "max_tokens"},
        reasoning_effort=None,
        max_tokens=None,
        capabilities=Capabilities(max_tokens=2048),
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(max_tokens=1024),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_tokens"] == 2048


def test_openai_completions_payload_respects_bridge_tool_name_developer_role_and_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            "supportsDeveloperRole": True,
            "requiresAssistantAfterToolResult": True,
            "requiresToolResultName": True,
            "supportsUsageInStreaming": False,
            "maxTokensField": "max_tokens",
        },
        reasoning_effort="high",
        base_url="https://api.openai.test/v1",
    )
    provider = OpenAICompletionsProvider()
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-completions",
        provider="openai",
        model="gpt-reasoning",
        response_id="resp_1",
        usage=Usage(
            input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
        ),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )
    tool_result = ToolResultMessage(
        role="toolResult",
        tool_call_id="call_1",
        tool_name="calc",
        content=[TextPart(type="text", text="42")],
        is_error=False,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(id="gpt-reasoning", reasoning=True),
                {
                    "system_prompt": "You reason carefully.",
                    "messages": [
                        assistant,
                        tool_result,
                        UserMessage(role="user", content="next", timestamp=0.0),
                    ],
                },
                OpenAICompletionsOptions(api_key="test-key", max_tokens=128),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["messages"] == [
        {"role": "developer", "content": "You reason carefully."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "calc", "arguments": '{"x": 1}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "calc",
            "content": "42",
        },
        {"role": "assistant", "content": "I have processed the tool results."},
        {"role": "user", "content": "next"},
    ]
    assert "stream_options" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["max_tokens"] == 128
    assert _FakeAsyncOpenAI.last_create_kwargs["reasoning_effort"] == "high"


def test_openai_completions_payload_uses_resolved_capabilities_for_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            "supportsDeveloperRole": True,
            "supportsReasoningEffort": True,
            "maxTokensField": "max_tokens",
        },
        reasoning_effort="high",
        capabilities=Capabilities(reasoning=True),
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(reasoning=False),
                {
                    "system_prompt": "You reason carefully.",
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["messages"][0] == {
        "role": "developer",
        "content": "You reason carefully.",
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["reasoning_effort"] == "high"


def test_openai_completions_payload_uses_typed_endpoint_dialect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    registry = get_default_model_registry()
    registry.register_endpoint(
        "typed",
        Endpoint(
            id="openai-completions",
            provider="typed",
            api="openai-completions",
            base_url="https://api.openai.test/v1",
            dialect=EndpointWireDialect.from_raw(
                {
                    "maxOutputTokensField": "max_tokens",
                    "tools": {
                        "resultNameRequired": True,
                        "assistantBridgeRequired": True,
                        "streamFlag": True,
                    },
                    "reasoning": {
                        "wireFormat": "moonshot",
                        "thinkingAsText": True,
                        "assistantContentRequired": True,
                    },
                    "cache": {
                        "controlFormat": "anthropic",
                    },
                }
            ),
            models={
                "gpt-test": Model(
                    id="gpt-test",
                    provider="typed",
                    endpoint="openai-completions",
                    capabilities=Capabilities(reasoning=True, tool_use=True),
                )
            },
        ),
    )
    model = registry.get_model("typed", "openai-completions", "gpt-test")
    provider = OpenAICompletionsProvider()
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ThinkingPart(
                type="thinking",
                thinking="plan",
                thinking_signature="reasoning_content",
            ),
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1}),
        ],
        api="openai-completions",
        provider="typed",
        model="gpt-test",
        response_id="resp_1",
        usage=Usage(
            input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
        ),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )
    tool_result = ToolResultMessage(
        role="toolResult",
        tool_call_id="call_1",
        tool_name="calc",
        content=[TextPart(type="text", text="42")],
        is_error=False,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                model,
                {
                    "system_prompt": "You are helpful.",
                    "messages": [
                        assistant,
                        tool_result,
                        UserMessage(role="user", content="next", timestamp=0.0),
                    ],
                    "tools": [
                        Tool(
                            name="calc",
                            description="Calculate values",
                            parameters={"type": "object"},
                        ),
                    ],
                },
                OpenAICompletionsOptions(
                    api_key="test-key",
                    max_tokens=128,
                    reasoning="high",
                    cache_retention="long",
                    session_id="session-1",
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_tokens"] == 128
    assert "max_completion_tokens" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["tool_stream"] is True
    assert _FakeAsyncOpenAI.last_create_kwargs["extra_body"] == {
        "thinking": {"type": "enabled"}
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-1"
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_retention"] == "24h"
    assert _FakeAsyncOpenAI.last_create_kwargs["tools"][0]["cache_control"] == {
        "type": "ephemeral",
        "ttl": "1h",
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["messages"][1] == {
        "role": "assistant",
        "content": "plan",
        "reasoning_content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "calc", "arguments": '{"x": 1}'},
            }
        ],
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["messages"][2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "calc",
        "content": "42",
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["messages"][3] == {
        "role": "assistant",
        "content": "I have processed the tool results.",
    }


def test_openai_completions_compat_detects_zai_thinking_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        reasoning_effort="high",
        base_url="https://api.z.ai/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(provider_id="zai", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["enable_thinking"] is True
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "store" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_compat_detects_qwen_thinking_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        reasoning_effort="high",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(provider_id="dashscope", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["enable_thinking"] is True
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["store"] is False


def test_openai_completions_compat_maps_qwen_chat_template_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={"thinkingFormat": "qwen-chat-template"},
        reasoning_effort="high",
        base_url="https://example-qwen-chat-template/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["chat_template_kwargs"] == {
        "enable_thinking": True,
        "preserve_thinking": True,
    }
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_typed_routing_maps_openrouter_provider_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        routing=EndpointRouting(
            request_overrides={"openrouter": {"only": ["anthropic"]}}
        ),
        reasoning_effort="high",
        base_url="https://openrouter.ai/api/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(provider_id="openrouter", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["reasoning"] == {"effort": "high"}
    assert _FakeAsyncOpenAI.last_create_kwargs["provider"] == {"only": ["anthropic"]}
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["store"] is False


def test_openai_completions_compat_maps_moonshot_thinking_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        reasoning_effort=None,
        base_url="https://api.moonshot.cn/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(provider_id="moonshot", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_compat_maps_moonshot_thinking_toggle_for_model_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        reasoning_effort=None,
        base_url="https://api.moonshot.cn/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                Model(
                    id="kimi-k2.5",
                    provider="moonshot",
                    endpoint="openai-completions",
                    capabilities=Capabilities(reasoning=True),
                ),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


def test_openai_completions_builtin_moonshot_uses_system_role_not_developer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    provider = OpenAICompletionsProvider()
    model = get_model("moonshot", "openai-completions", "kimi-k2.5")

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                model,
                {
                    "system_prompt": "You are helpful.",
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICompletionsOptions(),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["messages"][0] == {
        "role": "system",
        "content": "You are helpful.",
    }


def test_openai_completions_typed_routing_maps_vercel_gateway_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        routing=EndpointRouting(
            request_overrides={"vercelGateway": {"order": ["openai", "anthropic"]}}
        ),
        reasoning_effort=None,
        base_url="https://ai-gateway.vercel.sh/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["providerOptions"] == {
        "gateway": {"order": ["openai", "anthropic"]}
    }


def test_openai_completions_provider_adds_github_copilot_dynamic_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        reasoning_effort=None,
        base_url="https://api.githubcopilot.test/v1",
        extra_headers={"Editor-Version": "vscode/1.100.0"},
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(provider_id="github-copilot"),
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[
                                TextPart(type="text", text="look"),
                                ImagePart(
                                    type="image", data="dXNlcg==", mime_type="image/png"
                                ),
                            ],
                            timestamp=0.0,
                        ),
                        AssistantMessage(
                            role="assistant",
                            content=[
                                ToolCall(
                                    type="toolCall",
                                    id="call_1",
                                    name="calc",
                                    arguments={"x": 1},
                                ),
                            ],
                            api="openai-completions",
                            provider="github-copilot",
                            model="gpt-test",
                            response_id="resp_1",
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
                            tool_name="calc",
                            content=[
                                ImagePart(
                                    type="image", data="aGVsbG8=", mime_type="image/png"
                                ),
                            ],
                            is_error=False,
                            timestamp=0.0,
                        ),
                    ],
                },
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_init_kwargs["default_headers"] == {
        "Editor-Version": "vscode/1.100.0",
        "X-Initiator": "agent",
        "Openai-Intent": "conversation-edits",
        "Copilot-Vision-Request": "true",
    }


def test_openai_completions_payload_synthesizes_missing_tool_result_for_assistant_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, compat={}, reasoning_effort=None)
    provider = OpenAICompletionsProvider()
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-completions",
        provider="openai",
        model="gpt-test",
        response_id="resp_1",
        usage=Usage(
            input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
        ),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(),
                {"messages": [assistant]},
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["messages"] == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "calc", "arguments": '{"x": 1}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "No result provided",
        },
    ]


def test_openai_completions_uses_transport_timeout_when_options_omits_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        reasoning_effort=None,
        transport=EndpointTransport(timeout=12),
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(),
                {"messages": [{"role": "user", "content": "hello"}]},
                OpenAICompletionsOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_init_kwargs["timeout"] == 12


def test_openai_completions_stream_maps_thinking_tool_calls_and_reasoning_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(
        monkeypatch,
        chunks=[
            SimpleNamespace(
                id="chatcmpl_1",
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            reasoning_content="plan",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call_1",
                                    function=SimpleNamespace(
                                        name="calc", arguments='{"x":'
                                    ),
                                )
                            ],
                        ),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                id="chatcmpl_1",
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            tool_calls=[
                                SimpleNamespace(
                                    id="call_1",
                                    function=SimpleNamespace(arguments="1}"),
                                )
                            ],
                            reasoning_details=[
                                SimpleNamespace(
                                    type="reasoning.encrypted",
                                    id="call_1",
                                    data="secret",
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ],
                usage=None,
            ),
        ],
    )
    _patch_resolved_request(monkeypatch, compat={}, reasoning_effort=None)
    provider = OpenAICompletionsProvider()

    async def _scenario() -> list[dict]:
        stream = await provider.stream(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICompletionsOptions(api_key="test-key"),
        )
        return await _collect_stream_events(stream)

    events = asyncio.run(_scenario())

    assert [event["type"] for event in events] == [
        "start",
        "thinking_start",
        "thinking_delta",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_delta",
        "toolcall_end",
        "thinking_end",
        "done",
    ]
    done = events[-1]["message"]
    assert done.stop_reason == "toolUse"
    assert done.content[0].thinking == "plan"
    assert done.content[1].name == "calc"
    assert done.content[1].arguments == {"x": 1}
    assert (
        done.content[1].thought_signature
        == '{"type": "reasoning.encrypted", "id": "call_1", "data": "secret"}'
    )


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


async def _collect_stream_events(stream) -> list[dict]:
    return [event async for event in stream]


def _fake_openai_module(
    monkeypatch: pytest.MonkeyPatch, *, chunks: list[object] | None = None
) -> None:
    _FakeAsyncOpenAI.last_init_kwargs = {}
    _FakeAsyncOpenAI.last_create_kwargs = {}
    _FakeAsyncOpenAI.chunks = chunks or []
    module = ModuleType("openai")
    module.AsyncOpenAI = _FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)


def _patch_resolved_request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    compat: dict[str, object],
    reasoning_effort: str | None,
    base_url: str = "https://api.openai.test/v1",
    extra_headers: dict[str, str] | None = None,
    max_tokens: int | None = 1024,
    capabilities: Capabilities | None = None,
    routing: EndpointRouting | None = None,
    transport: EndpointTransport | None = None,
    upstream_model_id: str | None = None,
) -> None:
    def _resolve(provider_api, _model, *, options=None, request=None):
        if request is not None:
            if request.api != provider_api:
                raise ValueError(
                    f"Mismatched api: provider={provider_api!r} request.api={request.api!r}"
                )
            return request
        headers = {}
        api_key = getattr(options, "api_key", None) if options is not None else None
        if isinstance(api_key, str) and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)
        option_max_tokens = (
            getattr(options, "max_tokens", None) if options is not None else None
        )
        resolved_max_tokens = (
            max(1, option_max_tokens)
            if isinstance(option_max_tokens, int)
            else max_tokens
        )
        return ResolvedRequest(
            provider=getattr(_model, "provider_id", ""),
            endpoint=getattr(_model, "endpoint_id", ""),
            api=provider_api,
            base_url=base_url,
            headers=headers,
            adapter_compat=resolve_openai_completions_compat(
                provider_id=getattr(_model, "provider_id", ""),
                model_id=getattr(_model, "id", ""),
                base_url=base_url,
                raw=compat,
            ),
            max_tokens=resolved_max_tokens,
            capabilities=capabilities
            or Capabilities(
                input=tuple(getattr(_model, "input", ("text",))),
                reasoning=bool(getattr(_model, "reasoning", False)),
            ),
            reasoning_effort=reasoning_effort,
            routing=routing or EndpointRouting(),
            transport=transport or EndpointTransport(),
            upstream_model_id=upstream_model_id,
        )

    monkeypatch.setattr(
        "loushang.ai.providers.openai_completions.resolve_provider_request",
        _resolve,
    )


class _FakeAsyncOpenAI:
    last_init_kwargs: dict[str, object] = {}
    last_create_kwargs: dict[str, object] = {}
    chunks: list[object] = []

    def __init__(self, **kwargs) -> None:
        type(self).last_init_kwargs = kwargs
        self.chat = SimpleNamespace(completions=_FakeCompletions(type(self)))


class _FakeCompletions:
    def __init__(self, owner: type[_FakeAsyncOpenAI]) -> None:
        self._owner = owner

    async def create(self, **kwargs):
        self._owner.last_create_kwargs = kwargs
        return _FakeStream(self._owner.chunks)


class _FakeStream:
    def __init__(self, chunks: list[object]) -> None:
        self._iterator = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@dataclass(frozen=True)
class _Model:
    id: str = "gpt-test"
    base_url: str | None = None
    reasoning: bool = False
    input: tuple[str, ...] = ("text", "image")
    max_tokens: int | None = 4096
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, object] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    provider_id: str = "openai"
    endpoint_id: str = "openai-completions"


@pytest.fixture(autouse=True)
def _default_registry() -> Iterator[None]:
    def _endpoint(provider_id: str) -> Endpoint:
        return Endpoint(
            id="openai-completions",
            provider=provider_id,
            api="openai-completions",
            models={
                "gpt-test": Model(
                    id="gpt-test",
                    provider=provider_id,
                    endpoint="openai-completions",
                )
            },
        )

    clear_default_model_registry()
    registry = get_default_model_registry()
    for provider_id in [
        "openai",
        "zai",
        "dashscope",
        "openrouter",
        "github-copilot",
    ]:
        registry.register_endpoint(provider_id, _endpoint(provider_id))
    yield
    clear_default_model_registry()
