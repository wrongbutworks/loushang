from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai.advanced import OpenAIResponsesOptions
from loushang.ai.context import normalize_context
from loushang.ai.errors import UnsupportedCapabilityError
from loushang.ai.model import (
    Capabilities,
    Endpoint,
    EndpointTransport,
    Model,
    OpenAIResponsesConfig,
    Pricing,
    get_default_model_registry,
)
from loushang.ai.model.registry import clear_default_model_registry
from loushang.ai.provider import ResolvedRequest
from loushang.ai.providers.openai_responses import OpenAIResponsesProvider
from loushang.ai.providers.openai_responses_shared import process_responses_stream
from loushang.ai.structured import StructuredOutputOptions
from loushang.ai.types import (
    AssistantMessage,
    Context,
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


class _AsyncEventStream:
    def __init__(self, events: list[SimpleNamespace]) -> None:
        self._events = events

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self._events:
            yield event


async def _collect_raw_parts(events: list[SimpleNamespace]) -> list[dict[str, object]]:
    return [part async for part in process_responses_stream(_AsyncEventStream(events))]


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


def test_openai_responses_payload_maps_formal_context_and_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(),
                Context(
                    system_prompt="You are helpful.",
                    messages=[UserMessage(role="user", content="hello", timestamp=0.0)],
                    tools=[
                        Tool(
                            name="calc",
                            description="Calculate values",
                            parameters={"type": "object"},
                        )
                    ],
                ),
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": [{"type": "input_text", "text": "hello"}]},
    ]
    assert _FakeAsyncOpenAI.last_create_kwargs["tools"] == [
        {
            "type": "function",
            "name": "calc",
            "description": "Calculate values",
            "parameters": {"type": "object"},
        }
    ]


def test_openai_responses_payload_uses_resolved_capabilities_for_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        base_url="https://api.openai.test/v1",
        capabilities=Capabilities(input=("text", "image")),
    )
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(input=("text",)),
                Context(
                    system_prompt=None,
                    messages=[
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
                        ToolResultMessage(
                            role="toolResult",
                            tool_call_id="call_1",
                            tool_name="read",
                            content=[
                                ImagePart(
                                    type="image",
                                    data="dG9vbA==",
                                    mime_type="image/png",
                                )
                            ],
                            is_error=False,
                            timestamp=0.0,
                        ),
                    ],
                ),
                OpenAIResponsesOptions(api_key="test-key", pairing_mode="repair"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "look"},
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": "data:image/png;base64,dXNlcg==",
                },
            ],
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": [
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": "data:image/png;base64,dG9vbA==",
                }
            ],
        },
    ]


def test_openai_responses_payload_maps_structured_output_text_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        base_url="https://api.openai.test/v1",
        capabilities=Capabilities(input=("text",), structured_output=True),
    )
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(),
                Context(
                    messages=[UserMessage(role="user", content="hello", timestamp=0.0)]
                ),
                OpenAIResponsesOptions(
                    api_key="test-key",
                    output=StructuredOutputOptions(mode="json_object"),
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["text"] == {
        "format": {"type": "json_object"}
    }


def test_openai_responses_direct_stream_rejects_mismatched_request_api() -> None:
    provider = OpenAIResponsesProvider()
    request = ResolvedRequest(
        provider="openai",
        endpoint="openai-responses",
        api="openai-completions",
        base_url=None,
        capabilities=Capabilities(input=("text",)),
    )

    with pytest.raises(ValueError, match="Mismatched api"):
        asyncio.run(
            _stream(
                provider,
                _Model(),
                {"messages": [UserMessage(role="user", content="hello", timestamp=0)]},
                OpenAIResponsesOptions(),
                request,
            )
        )


def test_openai_responses_supplied_empty_request_uses_typed_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAIResponsesProvider()
    request = ResolvedRequest(
        provider="openai",
        endpoint="openai-responses",
        api="openai-responses",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        capabilities=Capabilities(input=("text",), reasoning=True),
        max_tokens=128,
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=True),
                Context(
                    system_prompt="Use terse answers.",
                    messages=[UserMessage(role="user", content="hello", timestamp=0.0)],
                ),
                OpenAIResponsesOptions(
                    cache_retention="long",
                    session_id="session-default",
                ),
                request,
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"][0] == {
        "role": "developer",
        "content": "Use terse answers.",
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-default"
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_retention"] == "24h"
    assert _FakeAsyncOpenAI.last_init_kwargs["default_headers"]["session_id"] == (
        "session-default"
    )


def test_openai_responses_supplied_request_adapter_config_projects_to_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAIResponsesProvider()
    request = ResolvedRequest(
        provider="openai",
        endpoint="openai-responses",
        api="openai-responses",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAIResponsesConfig(
            developer_role=False,
            assistant_after_tool_result=True,
            long_cache_retention=False,
            session_id_header=False,
        ),
        capabilities=Capabilities(input=("text",), reasoning=True),
        max_tokens=128,
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=True),
                _tool_result_followed_by_user_context(system_prompt="Use system."),
                OpenAIResponsesOptions(
                    cache_retention="short",
                    session_id="session-options",
                ),
                request,
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {"role": "system", "content": "Use system."},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "calc",
            "arguments": '{"x": 1}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "42",
        },
        {"role": "assistant", "content": "I have processed the tool results."},
        {"role": "user", "content": [{"type": "input_text", "text": "next"}]},
    ]
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-options"
    assert "prompt_cache_retention" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "session_id" not in _FakeAsyncOpenAI.last_init_kwargs["default_headers"]
    assert (
        _FakeAsyncOpenAI.last_init_kwargs["default_headers"]["x-client-request-id"]
        == "session-options"
    )


def test_openai_responses_rejects_unsupported_long_cache_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAIResponsesProvider()
    request = ResolvedRequest(
        provider="openai",
        endpoint="openai-responses",
        api="openai-responses",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAIResponsesConfig(long_cache_retention=False),
        capabilities=Capabilities(input=("text",), reasoning=True),
        max_tokens=128,
    )

    with pytest.raises(UnsupportedCapabilityError, match="long cache retention"):
        asyncio.run(
            _collect_parts(
                _stream_raw_parts(
                    provider,
                    _Model(reasoning=True),
                    Context(
                        system_prompt=None,
                        messages=[
                            UserMessage(role="user", content="hello", timestamp=0.0)
                        ],
                    ),
                    OpenAIResponsesOptions(cache_retention="long"),
                    request,
                )
            )
        )

    assert _FakeAsyncOpenAI.last_create_kwargs == {}


def test_openai_responses_supplied_request_typed_adapter_overrides_stale_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    provider = OpenAIResponsesProvider()
    request = ResolvedRequest(
        provider="openai",
        endpoint="openai-responses",
        api="openai-responses",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        adapter_config=OpenAIResponsesConfig(
            developer_role=False,
            assistant_after_tool_result=False,
            long_cache_retention=False,
            session_id_header=False,
        ),
        capabilities=Capabilities(input=("text",), reasoning=True),
        max_tokens=128,
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=True),
                _tool_result_followed_by_user_context(system_prompt="Use system."),
                OpenAIResponsesOptions(
                    cache_retention="short",
                    session_id="session-typed",
                ),
                request,
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {"role": "system", "content": "Use system."},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "calc",
            "arguments": '{"x": 1}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "42",
        },
        {"role": "user", "content": [{"type": "input_text", "text": "next"}]},
    ]
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-typed"
    assert "prompt_cache_retention" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "session_id" not in _FakeAsyncOpenAI.last_init_kwargs["default_headers"]


def test_openai_responses_uses_upstream_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        base_url="https://api.openai.test/v1",
        upstream_model_id="openai/gpt-oss-120b:free",
    )
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(id="openai/gpt-oss-120b_free"),
                Context(
                    system_prompt=None,
                    messages=[UserMessage(role="user", content="hello", timestamp=0.0)],
                ),
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["model"] == "openai/gpt-oss-120b:free"


def test_openai_responses_caps_model_max_tokens_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        base_url="https://api.openai.test/v1",
        max_tokens=None,
    )
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(max_tokens=32768),
                Context(
                    system_prompt=None,
                    messages=[UserMessage(role="user", content="hello", timestamp=0.0)],
                    tools=[],
                ),
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_output_tokens"] == 32000


def test_openai_responses_uses_resolved_capability_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        base_url="https://api.openai.test/v1",
        max_tokens=None,
        capabilities=Capabilities(max_tokens=2048),
    )
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(max_tokens=1024),
                Context(
                    system_prompt=None,
                    messages=[UserMessage(role="user", content="hello", timestamp=0.0)],
                    tools=[],
                ),
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["max_output_tokens"] == 2048


def test_openai_responses_payload_maps_assistant_tool_call_and_synthesizes_missing_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
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
            _stream_raw_parts(
                provider,
                _Model(),
                {"messages": [assistant]},
                OpenAIResponsesOptions(api_key="test-key", pairing_mode="repair"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "calc",
            "arguments": '{"x": 1}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "No result provided",
        },
    ]


def test_openai_responses_payload_normalizes_cross_provider_tool_call_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(
                type="toolCall", id="call:1|orig:item", name="calc", arguments={"x": 1}
            )
        ],
        api="anthropic-messages",
        provider="anthropic",
        model="claude-test",
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
        tool_call_id="call:1|orig:item",
        tool_name="calc",
        content=[TextPart(type="text", text="42")],
        is_error=False,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(),
                {"messages": [assistant, tool_result]},
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    function_call = _FakeAsyncOpenAI.last_create_kwargs["input"][0]
    function_output = _FakeAsyncOpenAI.last_create_kwargs["input"][1]
    assert function_call["type"] == "function_call"
    assert function_call["call_id"] == "call_1"
    assert function_call["id"].startswith("fc_")
    assert function_output == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "42",
    }


def test_openai_responses_payload_replays_assistant_thinking_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ThinkingPart(
                type="thinking",
                thinking="plan",
                thinking_signature='{"type":"reasoning","id":"rs_1","summary":[{"type":"summary_text","text":"plan"}]}',
            ),
            TextPart(type="text", text="done"),
        ],
        api="openai-responses",
        provider="openai",
        model="gpt-test",
        response_id="resp_1",
        usage=Usage(
            input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
        ),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(),
                {"messages": [assistant]},
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {
            "type": "reasoning",
            "id": "rs_1",
            "summary": [{"type": "summary_text", "text": "plan"}],
        },
        {"role": "assistant", "content": "done"},
    ]


def test_openai_responses_payload_replays_assistant_text_signature_and_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()
    assistant = AssistantMessage(
        role="assistant",
        content=[
            TextPart(
                type="text",
                text="done",
                text_signature='{"v":1,"id":"msg_1","phase":"commentary"}',
            ),
        ],
        api="openai-responses",
        provider="openai",
        model="gpt-test",
        response_id="resp_1",
        usage=Usage(
            input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
        ),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(),
                {"messages": [assistant]},
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {"role": "assistant", "content": "done", "id": "msg_1", "phase": "commentary"},
    ]


def test_openai_responses_payload_maps_reasoning_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=True),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAIResponsesOptions(
                    api_key="test-key",
                    reasoning="high",
                    reasoning_summary="detailed",
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["reasoning"] == {
        "effort": "high",
        "summary": "detailed",
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["include"] == [
        "reasoning.encrypted_content"
    ]


def test_openai_responses_payload_uses_resolved_capabilities_for_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        base_url="https://api.openai.test/v1",
        capabilities=Capabilities(reasoning=True),
    )
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=False),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAIResponsesOptions(
                    api_key="test-key",
                    reasoning="high",
                    reasoning_summary="detailed",
                ),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["reasoning"] == {
        "effort": "high",
        "summary": "detailed",
    }
    assert _FakeAsyncOpenAI.last_create_kwargs["include"] == [
        "reasoning.encrypted_content"
    ]


def test_openai_responses_payload_maps_tool_result_images_and_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        base_url="https://bridge.example/v1",
        compat={"requiresAssistantAfterToolResult": True},
    )
    provider = OpenAIResponsesProvider()
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
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
        ],
        is_error=False,
        timestamp=0.0,
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=True),
                {
                    "messages": [
                        assistant,
                        tool_result,
                        UserMessage(role="user", content="next", timestamp=0.0),
                    ]
                },
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "calc",
            "arguments": '{"x": 1}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": [
                {"type": "input_text", "text": "before"},
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": "data:image/png;base64,aGVsbG8=",
                },
            ],
        },
        {"role": "assistant", "content": "I have processed the tool results."},
        {"role": "user", "content": [{"type": "input_text", "text": "next"}]},
    ]


def test_openai_responses_provider_adds_github_copilot_dynamic_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        base_url="https://api.githubcopilot.test/v1",
        extra_headers={"Editor-Version": "vscode/1.100.0"},
        transport=EndpointTransport(kind="github-copilot"),
    )
    provider = OpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
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
                                )
                            ],
                            api="openai-responses",
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
                                )
                            ],
                            is_error=False,
                            timestamp=0.0,
                        ),
                    ]
                },
                OpenAIResponsesOptions(api_key="test-key"),
            )
        )
    )

    assert _FakeAsyncOpenAI.last_init_kwargs["default_headers"] == {
        "Editor-Version": "vscode/1.100.0",
        "X-Initiator": "agent",
        "Openai-Intent": "conversation-edits",
        "Copilot-Vision-Request": "true",
    }


def test_openai_responses_stream_applies_priority_service_tier_cost_multiplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = get_default_model_registry()
    registry.register_endpoint(
        "openai",
        Endpoint(
            id="responses",
            provider="openai",
            api="openai-responses",
        ),
    )
    registry.register_model(
        Model(
            id="gpt-test",
            provider="openai",
            endpoint="responses",
            pricing=Pricing(input=1.5, output=6.0, cache_read=0.3, cache_write=3.0),
        )
    )

    _fake_openai_module(
        monkeypatch,
        events=[
            SimpleNamespace(
                type="response.created", response=SimpleNamespace(id="resp_1")
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    status="completed",
                    service_tier="priority",
                    usage=SimpleNamespace(
                        input_tokens=2000,
                        output_tokens=500,
                        total_tokens=2500,
                        input_tokens_details=SimpleNamespace(cached_tokens=100),
                    ),
                ),
            ),
        ],
    )
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()

    stream = asyncio.run(
        _stream(
            provider,
            Model(
                id="gpt-test",
                provider="openai",
                endpoint="responses",
                pricing=Pricing(input=1.5, output=6.0, cache_read=0.3, cache_write=3.0),
            ),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAIResponsesOptions(api_key="test-key", service_tier="priority"),
        )
    )
    events = asyncio.run(_collect_stream_events(stream))

    message = events[-1]["message"]
    cost = message.usage.cost
    assert abs(cost["input"] - 0.0057) < 1e-9
    assert abs(cost["output"] - 0.006) < 1e-9
    assert abs(cost["cacheRead"] - 0.00006) < 1e-12
    assert (
        abs(cost["total"] - (cost["input"] + cost["output"] + cost["cacheRead"]))
        < 1e-12
    )


def test_openai_responses_stream_retains_thinking_signature_on_final_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(
        monkeypatch,
        events=[
            SimpleNamespace(
                type="response.created", response=SimpleNamespace(id="resp_1")
            ),
            SimpleNamespace(
                type="response.output_item.added",
                item=SimpleNamespace(type="reasoning", id="rs_1", summary=[]),
            ),
            SimpleNamespace(
                type="response.reasoning_summary_part.added",
                part=SimpleNamespace(type="summary_text", text=""),
            ),
            SimpleNamespace(type="response.reasoning_summary_text.delta", delta="plan"),
            SimpleNamespace(
                type="response.output_item.done",
                item=SimpleNamespace(
                    type="reasoning",
                    id="rs_1",
                    summary=[SimpleNamespace(type="summary_text", text="plan")],
                ),
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    status="completed",
                    usage=SimpleNamespace(
                        input_tokens=1,
                        output_tokens=1,
                        total_tokens=2,
                        input_tokens_details=SimpleNamespace(cached_tokens=0),
                    ),
                ),
            ),
        ],
    )
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()

    stream = asyncio.run(
        _stream(
            provider,
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAIResponsesOptions(api_key="test-key", reasoning="high"),
        )
    )
    events = asyncio.run(_collect_stream_events(stream))

    assert [event["type"] for event in events] == [
        "start",
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "done",
    ]
    assert events[-1]["message"].content[0].thinking == "plan"
    assert (
        events[-1]["message"].content[0].thinking_signature
        == '{"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "plan"}]}'
    )


def test_openai_responses_function_call_delta_uses_composite_call_id() -> None:
    parts = asyncio.run(
        _collect_raw_parts(
            [
                SimpleNamespace(
                    type="response.output_item.added",
                    output_index=1,
                    item=SimpleNamespace(
                        type="function_call",
                        id="fc_1",
                        call_id="call_1",
                        name="read",
                    ),
                ),
                SimpleNamespace(
                    type="response.function_call_arguments.delta",
                    item_id="fc_1",
                    output_index=1,
                    delta='{"path":',
                ),
                SimpleNamespace(
                    type="response.output_item.done",
                    output_index=1,
                    item=SimpleNamespace(
                        type="function_call",
                        id="fc_1",
                        call_id="call_1",
                    ),
                ),
            ]
        )
    )

    assert parts == [
        {
            "type": "tool_call_start",
            "id": "call_1|fc_1",
            "name": "read",
            "index": 1,
        },
        {
            "type": "tool_call_args_delta",
            "delta": '{"path":',
            "tool_call_id": "call_1|fc_1",
            "index": 1,
        },
        {
            "type": "tool_call_done",
            "tool_call_id": "call_1|fc_1",
            "index": 1,
        },
        {"type": "response_done"},
    ]


def test_openai_responses_stream_joins_multiple_reasoning_summary_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(
        monkeypatch,
        events=[
            SimpleNamespace(
                type="response.created", response=SimpleNamespace(id="resp_1")
            ),
            SimpleNamespace(
                type="response.output_item.added",
                item=SimpleNamespace(type="reasoning", id="rs_1", summary=[]),
            ),
            SimpleNamespace(
                type="response.reasoning_summary_part.added",
                part=SimpleNamespace(type="summary_text", text=""),
            ),
            SimpleNamespace(
                type="response.reasoning_summary_text.delta", delta="first"
            ),
            SimpleNamespace(type="response.reasoning_summary_part.done"),
            SimpleNamespace(
                type="response.reasoning_summary_part.added",
                part=SimpleNamespace(type="summary_text", text=""),
            ),
            SimpleNamespace(
                type="response.reasoning_summary_text.delta", delta="second"
            ),
            SimpleNamespace(
                type="response.output_item.done",
                item=SimpleNamespace(
                    type="reasoning",
                    id="rs_1",
                    summary=[
                        SimpleNamespace(type="summary_text", text="first"),
                        SimpleNamespace(type="summary_text", text="second"),
                    ],
                ),
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    status="completed",
                    usage=SimpleNamespace(
                        input_tokens=1,
                        output_tokens=1,
                        total_tokens=2,
                        input_tokens_details=SimpleNamespace(cached_tokens=0),
                    ),
                ),
            ),
        ],
    )
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()

    stream = asyncio.run(
        _stream(
            provider,
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAIResponsesOptions(api_key="test-key", reasoning="high"),
        )
    )
    events = asyncio.run(_collect_stream_events(stream))

    assert [event["type"] for event in events] == [
        "start",
        "thinking_start",
        "thinking_delta",
        "thinking_delta",
        "thinking_delta",
        "thinking_end",
        "done",
    ]
    assert events[-1]["message"].content[0].thinking == "first\n\nsecond"


def test_openai_responses_stream_retains_text_signature_on_final_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(
        monkeypatch,
        events=[
            SimpleNamespace(
                type="response.created", response=SimpleNamespace(id="resp_1")
            ),
            SimpleNamespace(
                type="response.output_item.added",
                item=SimpleNamespace(
                    type="message", id="msg_1", content=[], phase="final_answer"
                ),
            ),
            SimpleNamespace(type="response.output_text.delta", delta="Hello"),
            SimpleNamespace(
                type="response.output_item.done",
                item=SimpleNamespace(
                    type="message",
                    id="msg_1",
                    phase="final_answer",
                    content=[SimpleNamespace(type="output_text", text="Hello")],
                ),
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    status="completed",
                    usage=SimpleNamespace(
                        input_tokens=1,
                        output_tokens=1,
                        total_tokens=2,
                        input_tokens_details=SimpleNamespace(cached_tokens=0),
                    ),
                ),
            ),
        ],
    )
    _patch_resolved_request(monkeypatch, base_url="https://api.openai.test/v1")
    provider = OpenAIResponsesProvider()

    stream = asyncio.run(
        _stream(
            provider,
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAIResponsesOptions(api_key="test-key"),
        )
    )
    events = asyncio.run(_collect_stream_events(stream))

    assert [event["type"] for event in events] == [
        "start",
        "text_start",
        "text_delta",
        "text_end",
        "done",
    ]
    assert events[-1]["message"].content[0].text == "Hello"
    assert (
        events[-1]["message"].content[0].text_signature
        == '{"v": 1, "id": "msg_1", "phase": "final_answer"}'
    )


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


async def _collect_stream_events(stream) -> list[dict]:
    return [event async for event in stream]


def _tool_result_followed_by_user_context(*, system_prompt: str) -> Context:
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
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
        content=[TextPart(type="text", text="42")],
        is_error=False,
        timestamp=0.0,
    )
    return Context(
        system_prompt=system_prompt,
        messages=[
            assistant,
            tool_result,
            UserMessage(role="user", content="next", timestamp=0.0),
        ],
    )


def _fake_openai_module(
    monkeypatch: pytest.MonkeyPatch, *, events: list[object] | None = None
) -> None:
    _FakeAsyncOpenAI.last_init_kwargs = {}
    _FakeAsyncOpenAI.last_create_kwargs = {}
    _FakeAsyncOpenAI.events = events or [
        SimpleNamespace(type="response.created", response=SimpleNamespace(id="resp_1")),
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(
                status="completed",
                usage=SimpleNamespace(
                    input_tokens=1,
                    output_tokens=1,
                    total_tokens=2,
                    input_tokens_details=SimpleNamespace(cached_tokens=0),
                ),
            ),
        ),
    ]
    module = ModuleType("openai")
    module.AsyncOpenAI = _FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)


def _patch_resolved_request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    base_url: str,
    compat: dict[str, object] | None = None,
    adapter_config: OpenAIResponsesConfig | None = None,
    extra_headers: dict[str, str] | None = None,
    max_tokens: int | None = 1024,
    capabilities: Capabilities | None = None,
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
            adapter_config=adapter_config
            or _responses_adapter_config_from_compat(compat or {}),
            transport=transport or EndpointTransport(),
            max_tokens=resolved_max_tokens,
            capabilities=capabilities
            or Capabilities(
                input=tuple(getattr(_model, "input", ("text",))),
                reasoning=bool(getattr(_model, "reasoning", False)),
            ),
            upstream_model_id=upstream_model_id,
        )

    monkeypatch.setattr(
        "loushang.ai.providers.openai_responses.resolve_provider_request",
        _resolve,
    )


def _responses_adapter_config_from_compat(
    compat: dict[str, object],
) -> OpenAIResponsesConfig:
    return OpenAIResponsesConfig(
        developer_role=bool(compat.get("supportsDeveloperRole", True)),
        assistant_after_tool_result=bool(
            compat.get("requiresAssistantAfterToolResult", False)
        ),
        long_cache_retention=bool(compat.get("supportsLongCacheRetention", True)),
        prompt_cache_key=bool(compat.get("supportsPromptCacheKey", True)),
        session_id_header=bool(compat.get("sendSessionIdHeader", True)),
    )


class _FakeAsyncOpenAI:
    last_init_kwargs: dict[str, object] = {}
    last_create_kwargs: dict[str, object] = {}
    events: list[object] = []

    def __init__(self, **kwargs) -> None:
        type(self).last_init_kwargs = kwargs
        self.responses = _FakeResponses(type(self))


class _FakeResponses:
    def __init__(self, owner: type[_FakeAsyncOpenAI]) -> None:
        self._owner = owner

    async def create(self, **kwargs):
        self._owner.last_create_kwargs = kwargs
        return _FakeStream(self._owner.events)


class _FakeStream:
    def __init__(self, events: list[object]) -> None:
        self._iterator = iter(events)

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
    reasoning: bool = False
    input: tuple[str, ...] = ("text", "image")
    max_tokens: int | None = 4096
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, object] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    provider_id: str = "openai"
    endpoint_id: str = "openai-responses"


@pytest.fixture(autouse=True)
def _default_registry() -> None:
    def _endpoint(provider_id: str) -> Endpoint:
        return Endpoint(
            id="openai-responses",
            provider=provider_id,
            api="openai-responses",
            models={
                "gpt-test": Model(
                    id="gpt-test",
                    provider=provider_id,
                    endpoint="openai-responses",
                )
            },
        )

    clear_default_model_registry()
    registry = get_default_model_registry()
    for provider_id in ["openai", "github-copilot"]:
        registry.register_endpoint(provider_id, _endpoint(provider_id))
