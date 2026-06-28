from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai import CallOptions, ReasoningOptions, get_model
from loushang.ai.context import normalize_context
from loushang.ai.errors import UnsupportedCapabilityError
from loushang.ai.model import Capabilities, Model, OpenAICompletionsConfig
from loushang.ai.model.domain import (
    Endpoint,
    EndpointRouting,
    EndpointTransport,
)
from loushang.ai.model.registry import (
    clear_default_model_registry,
    get_default_model_registry,
)
from loushang.ai.provider import ProviderRequest
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.structured import StructuredOutputOptions
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
    provider_request_for_test,
    start_test_provider_stream,
)

MAX_TOKENS_FIELD = "maxTokensField"
REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES = (
    "requiresReasoningContentOnAssistantMessages"
)
SUPPORTS_DEVELOPER_ROLE = "supportsDeveloperRole"
SUPPORTS_LONG_CACHE_RETENTION = "supportsLongCacheRetention"
SUPPORTS_PROMPT_CACHE_KEY = "supportsPromptCacheKey"
SUPPORTS_REASONING_EFFORT = "supportsReasoningEffort"
SUPPORTS_STORE = "supportsStore"
SUPPORTS_STRICT_MODE = "supportsStrictMode"
THINKING_FORMAT = "thinkingFormat"


def _normalized_context(model, context, options=None):
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
    normalized_context = _normalized_context(model, context, options)
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
        _normalized_context(model, context, options),
        options,
        request=request,
    )


def _adapter_config_from_compat(
    compat: dict[str, object] | None,
) -> OpenAICompletionsConfig:
    raw: dict[str, object] = {}
    compat = compat or {}
    mappings = {
        SUPPORTS_STORE: "store",
        SUPPORTS_DEVELOPER_ROLE: "developerRole",
        SUPPORTS_REASONING_EFFORT: "reasoningEffort",
        "supportsUsageInStreaming": "streamingUsage",
        SUPPORTS_PROMPT_CACHE_KEY: "promptCacheKey",
        SUPPORTS_LONG_CACHE_RETENTION: "longCacheRetention",
        SUPPORTS_STRICT_MODE: "strictSchema",
        "requiresToolResultName": "toolResultName",
        "requiresAssistantAfterToolResult": "assistantAfterToolResult",
        REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES: ("assistantReasoningContent"),
    }
    for old_key, new_key in mappings.items():
        if old_key in compat:
            raw[new_key] = compat[old_key]
    if MAX_TOKENS_FIELD in compat:
        raw["maxOutputTokensField"] = compat[MAX_TOKENS_FIELD]
    if THINKING_FORMAT in compat and compat[THINKING_FORMAT] is not None:
        raw["reasoningFormat"] = compat[THINKING_FORMAT]
    return OpenAICompletionsConfig.from_raw(raw)


def _assert_no_session_hint_fields() -> None:
    assert "prompt_cache_key" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "prompt_cache_retention" not in _FakeAsyncOpenAI.last_create_kwargs
    headers = _FakeAsyncOpenAI.last_init_kwargs.get("default_headers") or {}
    assert "session_id" not in headers
    assert "x-client-request-id" not in headers
    assert "x-session-affinity" not in headers


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
            _invoke_raw_parts(
                provider,
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
                CallOptions(api_key="test-key", tool_choice="required"),
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


def test_openai_completions_complete_mode_maps_non_stream_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(
        monkeypatch,
        response=SimpleNamespace(
            id="chatcmpl_complete",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        reasoning_content="plan",
                        reasoning_details=[
                            {
                                "type": "reasoning.encrypted",
                                "id": "call_1",
                                "data": "secret",
                            }
                        ],
                        content="hello",
                        tool_calls=[
                            SimpleNamespace(
                                id=None,
                                function=SimpleNamespace(
                                    name="calc",
                                    arguments='{"x":1}',
                                ),
                            )
                        ],
                    ),
                    finish_reason="content_filter",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=3,
                completion_tokens=2,
                prompt_tokens_details=SimpleNamespace(cached_tokens=1),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=4),
            ),
        ),
    )
    _patch_resolved_request(
        monkeypatch,
        compat={"supportsUsageInStreaming": True},
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()
    request = ProviderRequest(
        provider="openai",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAICompletionsConfig(tool_stream=True),
        capabilities=Capabilities(input=("text",), tool_use=True),
    )

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
                            name="calc",
                            description="Calculate values",
                            parameters={"type": "object"},
                        ),
                    ],
                },
                CallOptions(api_key="test-key"),
                request=request,
                mode="complete",
            )
        )
    )

    assert "stream" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "stream_options" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "tool_stream" not in _FakeAsyncOpenAI.last_create_kwargs
    assert [part["type"] for part in parts] == [
        "response_start",
        "usage_delta",
        "thinking_delta",
        "tool_call_thought_signature",
        "text_delta",
        "tool_call_start",
        "tool_call_args_delta",
        "tool_call_done",
        "stop_reason",
        "response_error",
        "response_done",
    ]
    assert parts[1]["input"] == 2
    assert parts[1]["output"] == 6
    assert parts[1]["total_tokens"] == 9
    assert parts[2] == {"type": "thinking_delta", "text": "plan"}
    assert parts[3]["tool_call_id"] == "call_1"
    assert parts[5]["id"] == "tool_call_0"
    assert parts[6]["delta"] == '{"x":1}'
    assert parts[8] == {"type": "stop_reason", "stop_reason": "error"}


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
            _invoke_raw_parts(
                provider,
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
                CallOptions(api_key="test-key", pairing_mode="repair"),
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


def test_openai_completions_payload_maps_structured_output_response_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        reasoning_effort=None,
        capabilities=Capabilities(input=("text",), structured_output=True),
    )
    provider = OpenAICompletionsProvider()
    schema = {
        "title": "Answer",
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    api_key="test-key",
                    output=StructuredOutputOptions(
                        mode="json_schema",
                        schema=schema,
                        strict=True,
                    ),
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "Answer",
            "schema": schema,
            "strict": True,
        },
    }


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
            _invoke_raw_parts(
                provider,
                _Model(id="openai/gpt-oss-120b_free"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
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
            _invoke_raw_parts(
                provider,
                _Model(max_tokens=32768),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
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
            _invoke_raw_parts(
                provider,
                _Model(max_tokens=1024),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
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
            _invoke_raw_parts(
                provider,
                _Model(id="gpt-reasoning", reasoning=True),
                {
                    "system_prompt": "You reason carefully.",
                    "messages": [
                        assistant,
                        tool_result,
                        UserMessage(role="user", content="next", timestamp=0.0),
                    ],
                },
                CallOptions(api_key="test-key", max_output_tokens=128),
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
            _invoke_raw_parts(
                provider,
                _Model(reasoning=False),
                {
                    "system_prompt": "You reason carefully.",
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                CallOptions(api_key="test-key"),
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
            adapter=OpenAICompletionsConfig(
                prompt_cache_key=True,
                max_output_tokens_field="max_tokens",
                tool_result_name=True,
                assistant_after_tool_result=True,
                tool_stream=True,
                reasoning_format="moonshot",
                thinking_as_text=True,
                assistant_reasoning_content=True,
                cache_control_format="anthropic",
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
            _invoke_raw_parts(
                provider,
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
                CallOptions(
                    api_key="test-key",
                    max_output_tokens=128,
                    reasoning=ReasoningOptions(effort="high"),
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


def test_openai_completions_supplied_request_adapter_config_projects_to_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAICompletionsProvider()
    request = ProviderRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAICompletionsConfig(
            max_output_tokens_field="max_tokens",
            prompt_cache_key=True,
        ),
        max_tokens=128,
        capabilities=Capabilities(input=("text",), max_tokens=4096),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    cache_retention="long",
                    session_id="session-supplied",
                ),
                request=request,
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_tokens"] == 128
    assert "max_completion_tokens" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-supplied"
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_retention"] == "24h"


def test_openai_completions_supplied_empty_request_uses_adapter_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAICompletionsProvider()
    request = ProviderRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        max_tokens=128,
        capabilities=Capabilities(input=("text",), max_tokens=4096),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(),
                request=request,
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_completion_tokens"] == 128
    assert "max_tokens" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["stream_options"] == {
        "include_usage": True
    }


def test_openai_completions_supplied_request_preserves_explicit_unknown_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAICompletionsProvider()
    request = ProviderRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAICompletionsConfig(developer_role=False),
        capabilities=Capabilities(input=("text",), reasoning=True, max_tokens=4096),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(reasoning=True),
                {
                    "system_prompt": "You reason carefully.",
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                CallOptions(),
                request=request,
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["messages"][0] == {
        "role": "system",
        "content": "You reason carefully.",
    }


def test_openai_completions_supplied_request_protocol_and_dialect_project_to_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAICompletionsProvider()
    request = ProviderRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAICompletionsConfig(
            prompt_cache_key=True,
            max_output_tokens_field="max_completion_tokens",
        ),
        max_tokens=128,
        capabilities=Capabilities(input=("text",), max_tokens=4096),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    cache_retention="long",
                    session_id="session-typed",
                ),
                request=request,
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_completion_tokens"] == 128
    assert "max_tokens" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["stream_options"] == {
        "include_usage": True
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-typed"
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_retention"] == "24h"


def test_openai_completions_public_stream_uses_supplied_typed_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAICompletionsProvider()
    request = ProviderRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAICompletionsConfig(
            prompt_cache_key=True,
            max_output_tokens_field="max_completion_tokens",
        ),
        max_tokens=128,
        capabilities=Capabilities(input=("text",), max_tokens=4096),
    )

    async def _run() -> None:
        stream = await _stream(
            provider,
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            CallOptions(
                cache_retention="short",
                session_id="session-public",
            ),
            request=request,
        )
        await stream.result()

    asyncio.run(_run())

    assert _FakeAsyncOpenAI.last_create_kwargs["max_completion_tokens"] == 128
    assert "max_tokens" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-public"


def test_openai_completions_supplied_request_typed_adapter_overrides_stale_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAICompletionsProvider()
    request = ProviderRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAICompletionsConfig(prompt_cache_key=False),
        capabilities=Capabilities(input=("text",), max_tokens=4096),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    cache_retention="short",
                    session_id="session-stale",
                ),
                request=request,
            )
        )
    )

    _assert_no_session_hint_fields()


def test_openai_completions_supplied_request_typed_dialect_overrides_stale_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAICompletionsProvider()
    request = ProviderRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAICompletionsConfig(
            max_output_tokens_field="max_completion_tokens"
        ),
        max_tokens=128,
        capabilities=Capabilities(input=("text",), max_tokens=4096),
    )

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(),
                request=request,
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_completion_tokens"] == 128
    assert "max_tokens" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_prompt_cache_key_uses_explicit_support_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={SUPPORTS_PROMPT_CACHE_KEY: True},
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    api_key="test-key",
                    cache_retention="short",
                    session_id="session-short",
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-short"
    assert "prompt_cache_retention" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_explicit_prompt_cache_key_reaches_sdk_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    registry = get_default_model_registry()
    registry.register_endpoint(
        "custom-openai",
        Endpoint(
            id="openai-completions",
            provider="custom-openai",
            api="openai-completions",
            base_url="https://api.openai.com/v1",
            adapter=OpenAICompletionsConfig(prompt_cache_key=True),
            models={
                "gpt-test": Model(
                    id="gpt-test",
                    provider="custom-openai",
                    endpoint="openai-completions",
                    capabilities=Capabilities(input=("text",), max_tokens=4096),
                )
            },
        ),
    )
    model = registry.get_model("custom-openai", "openai-completions", "gpt-test")
    provider = OpenAICompletionsProvider()

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
                CallOptions(
                    api_key="test-key",
                    cache_retention="long",
                    session_id="session-official",
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_init_kwargs["base_url"] == "https://api.openai.com/v1"
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-official"
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_retention"] == "24h"


def test_openai_completions_rejects_unsupported_long_cache_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            SUPPORTS_LONG_CACHE_RETENTION: False,
            SUPPORTS_PROMPT_CACHE_KEY: True,
        },
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    with pytest.raises(UnsupportedCapabilityError, match="long cache retention"):
        asyncio.run(
            _collect_parts(
                _invoke_raw_parts(
                    provider,
                    _Model(),
                    {
                        "messages": [
                            UserMessage(role="user", content="hello", timestamp=0.0)
                        ]
                    },
                    CallOptions(
                        api_key="test-key",
                        cache_retention="long",
                        session_id="session-long",
                    ),
                )
            )
        )

    assert _FakeAsyncOpenAI.last_create_kwargs == {}


def test_openai_completions_official_url_ignores_unsupported_session_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    registry = get_default_model_registry()
    registry.register_endpoint(
        "custom-openai",
        Endpoint(
            id="openai-completions",
            provider="custom-openai",
            api="openai-completions",
            base_url="https://api.openai.com/v1",
            models={
                "gpt-test": Model(
                    id="gpt-test",
                    provider="custom-openai",
                    endpoint="openai-completions",
                    capabilities=Capabilities(input=("text",), max_tokens=4096),
                )
            },
        ),
    )
    model = registry.get_model("custom-openai", "openai-completions", "gpt-test")
    provider = OpenAICompletionsProvider()

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
                CallOptions(
                    api_key="test-key",
                    cache_retention="long",
                    session_id="session-official",
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_init_kwargs["base_url"] == "https://api.openai.com/v1"
    _assert_no_session_hint_fields()


def test_openai_completions_typed_prompt_cache_key_unsupported_disables_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    registry = get_default_model_registry()
    registry.register_endpoint(
        "custom-openai",
        Endpoint(
            id="openai-completions",
            provider="custom-openai",
            api="openai-completions",
            base_url="https://api.openai.com/v1",
            adapter=OpenAICompletionsConfig(prompt_cache_key=False),
            models={
                "gpt-test": Model(
                    id="gpt-test",
                    provider="custom-openai",
                    endpoint="openai-completions",
                    capabilities=Capabilities(input=("text",), max_tokens=4096),
                )
            },
        ),
    )
    model = registry.get_model("custom-openai", "openai-completions", "gpt-test")
    provider = OpenAICompletionsProvider()

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
                CallOptions(
                    api_key="test-key",
                    cache_retention="long",
                    session_id="session-official",
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_init_kwargs["base_url"] == "https://api.openai.com/v1"
    _assert_no_session_hint_fields()


def test_openai_completions_prompt_cache_key_defaults_off_for_short_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, compat={}, reasoning_effort=None)
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    api_key="test-key",
                    cache_retention="short",
                    session_id="session-short",
                ),
            )
        )
    )

    _assert_no_session_hint_fields()


def test_openai_completions_prompt_cache_key_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={SUPPORTS_PROMPT_CACHE_KEY: False},
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    api_key="test-key",
                    cache_retention="short",
                    session_id="session-short",
                ),
            )
        )
    )

    _assert_no_session_hint_fields()


def test_openai_completions_prompt_cache_key_disables_long_retention_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            SUPPORTS_LONG_CACHE_RETENTION: True,
            SUPPORTS_PROMPT_CACHE_KEY: False,
        },
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(
                    api_key="test-key",
                    cache_retention="long",
                    session_id="session-long",
                ),
            )
        )
    )

    _assert_no_session_hint_fields()


def test_openai_completions_explicit_zai_thinking_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            THINKING_FORMAT: "zai",
            SUPPORTS_DEVELOPER_ROLE: False,
            SUPPORTS_REASONING_EFFORT: False,
            SUPPORTS_STORE: False,
        },
        reasoning_effort="high",
        base_url="https://api.z.ai/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="zai", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["enable_thinking"] is True
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "store" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_explicit_zai_thinking_object_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            THINKING_FORMAT: "zai-thinking",
            SUPPORTS_DEVELOPER_ROLE: False,
            SUPPORTS_REASONING_EFFORT: False,
            SUPPORTS_STORE: False,
        },
        reasoning_effort="high",
        base_url="https://api.z.ai/api/paas/v4/",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="zai", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["thinking"] == {"type": "enabled"}
    assert "enable_thinking" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "store" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_deepseek_thinking_uses_extra_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            THINKING_FORMAT: "deepseek",
            REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES: True,
            SUPPORTS_DEVELOPER_ROLE: False,
            SUPPORTS_REASONING_EFFORT: False,
            SUPPORTS_STORE: False,
        },
        reasoning_effort="high",
        base_url="https://api.deepseek.com",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="deepseek", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["extra_body"] == {
        "thinking": {"type": "enabled"}
    }
    assert "thinking" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "store" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_explicit_qwen_thinking_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            THINKING_FORMAT: "qwen",
            SUPPORTS_REASONING_EFFORT: False,
        },
        reasoning_effort="high",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="dashscope", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
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
            _invoke_raw_parts(
                provider,
                _Model(reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
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
        compat={
            THINKING_FORMAT: "openrouter",
            SUPPORTS_REASONING_EFFORT: False,
        },
        routing=EndpointRouting(
            request_overrides={"openrouter": {"only": ["anthropic"]}}
        ),
        reasoning_effort="high",
        base_url="https://openrouter.ai/api/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="openrouter", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["reasoning"] == {"effort": "high"}
    assert _FakeAsyncOpenAI.last_create_kwargs["provider"] == {"only": ["anthropic"]}
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["store"] is False


def test_openai_completions_mixed_routing_without_single_namespace_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={THINKING_FORMAT: "openrouter"},
        routing=EndpointRouting(
            request_overrides={
                "openrouter": {"only": ["anthropic"]},
                "vercelGateway": {"order": ["openai"]},
            }
        ),
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    with pytest.raises(ValueError, match="Ambiguous provider routing"):
        asyncio.run(
            _collect_parts(
                _invoke_raw_parts(
                    provider,
                    _Model(provider_id="openrouter"),
                    {
                        "messages": [
                            UserMessage(role="user", content="hello", timestamp=0.0)
                        ]
                    },
                    CallOptions(api_key="test-key"),
                )
            )
        )
    assert _FakeAsyncOpenAI.last_create_kwargs == {}


def test_openai_completions_mixed_routing_errors_independent_of_provider_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={THINKING_FORMAT: "openrouter"},
        routing=EndpointRouting(
            request_overrides={
                "openrouter": {"only": ["anthropic"]},
                "vercelGateway": {"order": ["openai"]},
            }
        ),
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    with pytest.raises(ValueError, match="Ambiguous provider routing"):
        asyncio.run(
            _collect_parts(
                _invoke_raw_parts(
                    provider,
                    _Model(provider_id="vercel-ai-gateway"),
                    {
                        "messages": [
                            UserMessage(role="user", content="hello", timestamp=0.0)
                        ]
                    },
                    CallOptions(api_key="test-key"),
                )
            )
        )
    assert _FakeAsyncOpenAI.last_create_kwargs == {}


def test_openai_completions_mixed_routing_errors_independent_of_base_url_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={THINKING_FORMAT: "openrouter"},
        routing=EndpointRouting(
            request_overrides={
                "openrouter": {"only": ["anthropic"]},
                "vercelGateway": {"order": ["openai"]},
            }
        ),
        reasoning_effort=None,
        base_url="https://openrouter.ai/api/v1",
    )
    provider = OpenAICompletionsProvider()

    with pytest.raises(ValueError, match="Ambiguous provider routing"):
        asyncio.run(
            _collect_parts(
                _invoke_raw_parts(
                    provider,
                    _Model(provider_id="custom"),
                    {
                        "messages": [
                            UserMessage(role="user", content="hello", timestamp=0.0)
                        ]
                    },
                    CallOptions(api_key="test-key"),
                )
            )
        )
    assert _FakeAsyncOpenAI.last_create_kwargs == {}


def test_openai_completions_vercel_routing_is_explicit_not_provider_inferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={THINKING_FORMAT: "openrouter"},
        routing=EndpointRouting(
            request_overrides={"vercelGateway": {"order": ["openai"]}}
        ),
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="openrouter"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert "provider" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["providerOptions"] == {
        "gateway": {"order": ["openai"]}
    }


def test_openai_completions_openrouter_routing_is_explicit_not_provider_inferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={},
        routing=EndpointRouting(
            request_overrides={"openrouter": {"only": ["anthropic"]}}
        ),
        reasoning_effort=None,
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="vercel-ai-gateway"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["provider"] == {"only": ["anthropic"]}
    assert "providerOptions" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_explicit_moonshot_thinking_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            THINKING_FORMAT: "moonshot",
            MAX_TOKENS_FIELD: "max_tokens",
            SUPPORTS_DEVELOPER_ROLE: False,
            SUPPORTS_REASONING_EFFORT: False,
            SUPPORTS_STORE: False,
            SUPPORTS_STRICT_MODE: False,
        },
        reasoning_effort=None,
        base_url="https://api.moonshot.cn/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="moonshot", reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert "reasoning_effort" not in _FakeAsyncOpenAI.last_create_kwargs


def test_openai_completions_explicit_moonshot_thinking_for_model_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        compat={
            THINKING_FORMAT: "moonshot",
            MAX_TOKENS_FIELD: "max_tokens",
            SUPPORTS_DEVELOPER_ROLE: False,
            SUPPORTS_REASONING_EFFORT: False,
            SUPPORTS_STORE: False,
            SUPPORTS_STRICT_MODE: False,
        },
        reasoning_effort=None,
        base_url="https://api.moonshot.cn/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                Model(
                    id="kimi-k2.6",
                    provider="moonshot",
                    endpoint="openai-completions",
                    capabilities=Capabilities(reasoning=True),
                ),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
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
    model = get_model("moonshot", "openai-completions", "kimi-k2.6")

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                model,
                {
                    "system_prompt": "You are helpful.",
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                CallOptions(),
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
        base_url="https://custom-gateway.example/v1",
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
                _Model(provider_id="vercel-ai-gateway"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["providerOptions"] == {
        "gateway": {"order": ["openai", "anthropic"]}
    }


def test_openai_completions_typed_routing_uses_explicit_single_namespace(
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
            _invoke_raw_parts(
                provider,
                _Model(provider_id="custom"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert "provider" not in _FakeAsyncOpenAI.last_create_kwargs
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
        transport=EndpointTransport(kind="github-copilot"),
    )
    provider = OpenAICompletionsProvider()

    asyncio.run(
        _collect_parts(
            _invoke_raw_parts(
                provider,
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
                CallOptions(api_key="test-key"),
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
            _invoke_raw_parts(
                provider,
                _Model(),
                {"messages": [assistant]},
                CallOptions(api_key="test-key", pairing_mode="repair"),
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
            _invoke_raw_parts(
                provider,
                _Model(),
                {"messages": [{"role": "user", "content": "hello"}]},
                CallOptions(api_key="test-key"),
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
        stream = await _stream(
            provider,
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            CallOptions(api_key="test-key"),
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


def test_openai_completions_stream_groups_interleaved_parallel_tool_calls(
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
                            tool_calls=[
                                SimpleNamespace(
                                    id="call_a",
                                    index=0,
                                    function=SimpleNamespace(
                                        name="add", arguments='{"a":'
                                    ),
                                ),
                                SimpleNamespace(
                                    id="call_b",
                                    index=1,
                                    function=SimpleNamespace(
                                        name="mul", arguments='{"x":'
                                    ),
                                ),
                            ]
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
                                    index=1,
                                    function=SimpleNamespace(arguments="2}"),
                                ),
                                SimpleNamespace(
                                    index=0,
                                    function=SimpleNamespace(arguments="1}"),
                                ),
                            ]
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
        stream = await _stream(
            provider,
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            CallOptions(api_key="test-key"),
        )
        return await _collect_stream_events(stream)

    events = asyncio.run(_scenario())

    assert [event["type"] for event in events] == [
        "start",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_delta",
        "toolcall_delta",
        "toolcall_end",
        "toolcall_end",
        "done",
    ]
    done = events[-1]["message"]
    assert [part.id for part in done.content] == ["call_a", "call_b"]
    assert [part.name for part in done.content] == ["add", "mul"]
    assert done.content[0].arguments == {"a": 1}
    assert done.content[1].arguments == {"x": 2}


def test_openai_completions_omits_response_start_when_chunk_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(
        monkeypatch,
        chunks=[
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="hello"),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            )
        ],
    )
    _patch_resolved_request(monkeypatch, compat={}, reasoning_effort=None)
    provider = OpenAICompletionsProvider()

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
                CallOptions(api_key="test-key"),
            )
        )
    )

    assert "response_start" not in {part["type"] for part in parts}
    assert {"type": "text_delta", "text": "hello"} in parts
    assert parts[-1] == {"type": "response_done"}


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


async def _collect_stream_events(stream) -> list[dict]:
    return [event async for event in stream]


def _fake_openai_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chunks: list[object] | None = None,
    response: object | None = None,
) -> None:
    _FakeAsyncOpenAI.last_init_kwargs = {}
    _FakeAsyncOpenAI.last_create_kwargs = {}
    _FakeAsyncOpenAI.chunks = chunks or []
    _FakeAsyncOpenAI.response = response
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
    def _resolve(_model, *, context=None, options=None, request=None):
        del context, request
        headers = {}
        api_key = getattr(options, "api_key", None) if options is not None else None
        if isinstance(api_key, str) and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)
        option_max_tokens = (
            getattr(options, "max_output_tokens", None) if options is not None else None
        )
        resolved_max_tokens = (
            max(1, option_max_tokens)
            if isinstance(option_max_tokens, int)
            else max_tokens
        )
        adapter_config = _adapter_config_from_compat(compat)
        return ProviderRequest(
            provider=getattr(_model, "provider_id", ""),
            endpoint=getattr(_model, "endpoint_id", ""),
            api="openai-completions",
            base_url=base_url,
            headers=headers,
            adapter_config=adapter_config,
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
        "tests.providers._runtime.resolve_request_for_model",
        _resolve,
    )


class _FakeAsyncOpenAI:
    last_init_kwargs: dict[str, object] = {}
    last_create_kwargs: dict[str, object] = {}
    chunks: list[object] = []
    response: object | None = None

    def __init__(self, **kwargs) -> None:
        type(self).last_init_kwargs = kwargs
        self.chat = SimpleNamespace(completions=_FakeCompletions(type(self)))


class _FakeCompletions:
    def __init__(self, owner: type[_FakeAsyncOpenAI]) -> None:
        self._owner = owner

    async def create(self, **kwargs):
        self._owner.last_create_kwargs = kwargs
        if kwargs.get("stream") is not True:
            return self._owner.response
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
        "vercel-ai-gateway",
        "custom",
        "github-copilot",
    ]:
        registry.register_endpoint(provider_id, _endpoint(provider_id))
    yield
    clear_default_model_registry()
