from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest

from loushang.ai.auth.types import OAuthCredentials
from loushang.ai.context import normalize_context
from loushang.ai.contrib.openai_codex import OpenAICodexResponsesOptions
from loushang.ai.contrib.openai_codex.provider import OpenAICodexResponsesProvider
from loushang.ai.model.domain import Compat, Endpoint, Model
from loushang.ai.model.registry import (
    clear_default_model_registry,
    get_default_model_registry,
)
from loushang.ai.options import RetryOptions
from loushang.ai.provider import ResolvedRequest
from loushang.ai.structured import StructuredOutputOptions
from loushang.ai.types import (
    AssistantMessage,
    TextPart,
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


def test_openai_codex_responses_builds_request_body_and_headers() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.created", "response": {"id": "resp_1"}},
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "total_tokens": 2,
                        "input_tokens_details": {"cached_tokens": 0},
                    },
                },
            },
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    model = _Model(reasoning=True)
    token = _build_fake_jwt("acc_test")

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                model,
                {
                    "system_prompt": "You are Codex.",
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                    "tools": [
                        Tool(
                            name="calc",
                            description="Calculate",
                            parameters={"type": "object"},
                        )
                    ],
                },
                OpenAICodexResponsesOptions(
                    api_key=token,
                    session_id="sess_1",
                    reasoning="minimal",
                    reasoning_summary="concise",
                    text_verbosity="high",
                ),
            )
        )
    )

    assert client.last_url == "https://chatgpt.com/backend-api/codex/responses"
    assert client.last_headers["Authorization"] == f"Bearer {token}"
    assert client.last_headers["chatgpt-account-id"] == "acc_test"
    assert client.last_headers["originator"] == "loushang"
    assert client.last_headers["OpenAI-Beta"] == "responses=experimental"
    assert client.last_headers["accept"] == "text/event-stream"
    assert client.last_headers["content-type"] == "application/json"
    assert client.last_headers["session_id"] == "sess_1"
    assert client.last_headers["x-client-request-id"] == "sess_1"
    assert "conversation_id" not in client.last_headers

    assert client.last_json == {
        "model": "gpt-5.3-codex",
        "store": False,
        "stream": True,
        "instructions": "You are Codex.",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "hello"}]}
        ],
        "tools": [
            {
                "type": "function",
                "name": "calc",
                "description": "Calculate",
                "parameters": {"type": "object"},
            }
        ],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "text": {"verbosity": "high"},
        "include": ["reasoning.encrypted_content"],
        "prompt_cache_key": "sess_1",
        "prompt_cache_retention": "in-memory",
        "reasoning": {"effort": "low", "summary": "concise"},
    }


def test_openai_codex_responses_merges_structured_output_text_format() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    token = _build_fake_jwt("acc_test")

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                OpenAICodexResponsesOptions(
                    api_key=token,
                    text_verbosity="low",
                    output=StructuredOutputOptions(mode="json_object"),
                ),
            )
        )
    )

    assert client.last_json["text"] == {
        "verbosity": "low",
        "format": {"type": "json_object"},
    }


def test_openai_codex_responses_preserves_tool_history_payload() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    token = _build_fake_jwt("acc_test")
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-codex-responses",
        provider="openai-codex",
        model="gpt-5.3-codex",
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
            _stream_raw_parts(
                provider,
                _Model(reasoning=False),
                {
                    "messages": [
                        assistant,
                        tool_result,
                        UserMessage(role="user", content="next", timestamp=0.0),
                    ],
                },
                OpenAICodexResponsesOptions(api_key=token),
            )
        )
    )

    assert client.last_json["input"] == [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "calc",
            "arguments": '{"x": 1}',
        },
        {"type": "function_call_output", "call_id": "call_1", "output": "42"},
        {"role": "user", "content": [{"type": "input_text", "text": "next"}]},
    ]


def test_openai_codex_responses_uses_upstream_model_id() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    token = _build_fake_jwt("acc_test")
    clear_default_model_registry()
    registry = get_default_model_registry()
    registry.register_endpoint(
        "openai-codex",
        Endpoint(
            id="openai-codex-responses",
            provider="openai-codex",
            api="openai-codex-responses",
            compat=Compat.from_raw(
                {
                    "codexIncludeClientRequestId": True,
                    "codexPromptCacheRetention": "in-memory",
                    "codexOriginator": "loushang",
                    "codexUserAgent": "loushang",
                }
            ),
            models={
                "gpt-5.3-codex_public": Model(
                    id="gpt-5.3-codex_public",
                    provider="openai-codex",
                    endpoint="openai-codex-responses",
                    upstream_id="gpt-5.3-codex",
                )
            },
        ),
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(id="gpt-5.3-codex_public"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICodexResponsesOptions(api_key=token),
            )
        )
    )

    assert client.last_json["model"] == "gpt-5.3-codex"


def test_openai_codex_responses_omits_optional_request_fields_when_unused() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    token = _build_fake_jwt("acc_test")

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=False),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICodexResponsesOptions(api_key=token),
            )
        )
    )

    assert client.last_json["instructions"] == ""
    assert "tools" not in client.last_json
    assert "tool_choice" not in client.last_json
    assert "parallel_tool_calls" not in client.last_json
    assert "reasoning" not in client.last_json
    assert "prompt_cache_key" not in client.last_json
    assert "prompt_cache_retention" not in client.last_json
    assert "session_id" not in client.last_headers
    assert "conversation_id" not in client.last_headers
    assert "x-client-request-id" not in client.last_headers


def test_openai_codex_responses_sends_empty_instructions_when_missing() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=False),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICodexResponsesOptions(api_key=_build_fake_jwt("acc_test")),
            )
        )
    )

    assert client.last_json["instructions"] == ""


def test_openai_codex_responses_respects_compat_session_headers() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    get_default_model_registry().register_endpoint(
        "openai-codex",
        Endpoint(
            id="openai-codex-responses",
            provider="openai-codex",
            api="openai-codex-responses",
            compat=Compat.from_raw(
                {
                    "codexIncludeClientRequestId": False,
                    "codexIncludeConversationId": True,
                    "codexPromptCacheRetention": "ephemeral",
                    "codexOriginator": "compat-test",
                    "codexUserAgent": "compat-agent",
                }
            ),
            models={
                "gpt-5.3-codex": Model(
                    id="gpt-5.3-codex",
                    provider="openai-codex",
                    endpoint="openai-codex-responses",
                )
            },
        ),
    )
    model = get_default_model_registry().get_model(
        "openai-codex",
        "openai-codex-responses",
        "gpt-5.3-codex",
    )
    provider = OpenAICodexResponsesProvider(client=client)
    token = _build_fake_jwt("acc_test")

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                model,
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICodexResponsesOptions(api_key=token, session_id="sess_compat"),
            )
        )
    )

    assert client.last_headers["session_id"] == "sess_compat"
    assert client.last_headers["conversation_id"] == "sess_compat"
    assert "x-client-request-id" not in client.last_headers
    assert client.last_headers["originator"] == "compat-test"
    assert client.last_headers["User-Agent"] == "compat-agent"
    assert client.last_json["prompt_cache_retention"] == "ephemeral"


def test_openai_codex_responses_public_stream_uses_runtime_config_headers() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    get_default_model_registry().register_endpoint(
        "openai-codex",
        Endpoint(
            id="openai-codex-responses",
            provider="openai-codex",
            api="openai-codex-responses",
            compat=Compat.from_raw(
                {
                    "codexIncludeClientRequestId": False,
                    "codexIncludeConversationId": True,
                    "codexPromptCacheRetention": "ephemeral",
                    "codexOriginator": "compat-public",
                    "codexUserAgent": "compat-public-agent",
                }
            ),
            models={
                "gpt-5.3-codex": Model(
                    id="gpt-5.3-codex",
                    provider="openai-codex",
                    endpoint="openai-codex-responses",
                )
            },
        ),
    )
    model = get_default_model_registry().get_model(
        "openai-codex",
        "openai-codex-responses",
        "gpt-5.3-codex",
    )
    provider = OpenAICodexResponsesProvider(client=client)

    async def _run() -> list[dict]:
        stream = await _stream(
            provider,
            model,
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(
                api_key=_build_fake_jwt("acc_test"),
                session_id="sess_public_config",
            ),
        )
        return await _collect_stream_events(stream)

    events = asyncio.run(_run())

    assert events[-1]["type"] == "done"
    assert client.last_headers["session_id"] == "sess_public_config"
    assert client.last_headers["conversation_id"] == "sess_public_config"
    assert "x-client-request-id" not in client.last_headers
    assert client.last_headers["originator"] == "compat-public"
    assert client.last_headers["User-Agent"] == "compat-public-agent"
    assert client.last_json["prompt_cache_retention"] == "ephemeral"


def test_openai_codex_responses_prefers_oauth_account_binding_over_token_parsing() -> (
    None
):
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=False),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICodexResponsesOptions(
                    oauth_credentials={
                        "openai-codex": OAuthCredentials(
                            provider="openai-codex",
                            access_token="not-a-jwt",
                            extra={"account_id": "acc_from_oauth", "plan": "pro"},
                        )
                    }
                ),
            )
        )
    )

    assert client.last_headers["Authorization"] == "Bearer not-a-jwt"
    assert client.last_headers["chatgpt-account-id"] == "acc_from_oauth"


def test_openai_codex_responses_uses_resolved_request_account_binding() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    request = ResolvedRequest(
        provider="openai-codex",
        endpoint="openai-codex-responses",
        api="openai-codex-responses",
        base_url=None,
        headers={"Authorization": "Bearer not-a-jwt"},
        auth_account_id="acc_from_resolved",
    )

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=False),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICodexResponsesOptions(),
                request,
            )
        )
    )

    assert client.last_headers["Authorization"] == "Bearer not-a-jwt"
    assert client.last_headers["chatgpt-account-id"] == "acc_from_resolved"


def test_openai_codex_responses_header_override_keeps_account_consistent() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    override_token = _build_fake_jwt("acc_header")

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=False),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                },
                OpenAICodexResponsesOptions(
                    oauth_credentials={
                        "openai-codex": OAuthCredentials(
                            provider="openai-codex",
                            access_token="not-a-jwt",
                            extra={"account_id": "acc_from_oauth"},
                        )
                    },
                    headers={
                        "Authorization": f"Bearer {override_token}",
                        "chatgpt-account-id": "acc_header",
                    },
                ),
            )
        )
    )

    assert client.last_headers["Authorization"] == f"Bearer {override_token}"
    assert client.last_headers["chatgpt-account-id"] == "acc_header"


def test_openai_codex_responses_stream_maps_sse_to_final_message() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.created", "response": {"id": "resp_1"}},
            {
                "type": "response.output_item.added",
                "item": {"type": "reasoning", "id": "rs_1", "summary": []},
            },
            {
                "type": "response.reasoning_summary_part.added",
                "part": {"type": "summary_text", "text": ""},
            },
            {"type": "response.reasoning_summary_text.delta", "delta": "plan"},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "reasoning",
                    "id": "rs_1",
                    "summary": [{"type": "summary_text", "text": "plan"}],
                },
            },
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "message",
                    "id": "msg_1",
                    "content": [],
                    "phase": "final_answer",
                },
            },
            {"type": "response.output_text.delta", "delta": "Hello"},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "id": "msg_1",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "Hello"}],
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {
                        "input_tokens": 3,
                        "output_tokens": 2,
                        "total_tokens": 5,
                        "input_tokens_details": {"cached_tokens": 1},
                    },
                },
            },
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=True),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(
                api_key=_build_fake_jwt("acc_test"), reasoning="high"
            ),
        )
    )
    events = asyncio.run(_collect_stream_events(stream))

    assert [event["type"] for event in events] == [
        "start",
        "thinking_start",
        "thinking_delta",
        "text_start",
        "text_delta",
        "thinking_end",
        "text_end",
        "done",
    ]
    message = events[-1]["message"]
    assert message.response_id == "resp_1"
    assert message.content[0].thinking == "plan"
    assert message.content[1].text == "Hello"
    assert message.usage.input == 2
    assert message.usage.output == 2
    assert message.usage.cache_read == 1


def test_openai_codex_responses_stream_handles_incomplete_and_refusal_events() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.created", "response": {"id": "resp_2"}},
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "message",
                    "id": "msg_2",
                    "content": [],
                    "phase": "commentary",
                },
            },
            {
                "type": "response.content_part.added",
                "part": {"type": "output_text", "text": ""},
            },
            {"type": "response.refusal.delta", "delta": "Denied"},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "id": "msg_2",
                    "phase": "commentary",
                    "content": [{"type": "refusal", "refusal": "Denied"}],
                },
            },
            {
                "type": "response.incomplete",
                "response": {
                    "status": "incomplete",
                    "usage": {
                        "input_tokens": 4,
                        "output_tokens": 1,
                        "total_tokens": 5,
                        "input_tokens_details": {"cached_tokens": 0},
                    },
                },
            },
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(api_key=_build_fake_jwt("acc_test")),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert events[-1]["type"] == "done"
    assert events[-1]["message"].stop_reason == "length"
    assert events[-1]["message"].content[0].text == "Denied"


def test_openai_codex_responses_stream_handles_error_event() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.created", "response": {"id": "resp_3"}},
            {"type": "error", "code": "rate_limit", "message": "Try later"},
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(api_key=_build_fake_jwt("acc_test")),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert events[-1]["type"] == "error"
    assert events[-1]["error"].error_message == "Error Code rate_limit: Try later"


def test_openai_codex_responses_stream_handles_response_done_alias() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.created", "response": {"id": "resp_4"}},
            {
                "type": "response.output_item.added",
                "item": {"type": "message", "id": "msg_4", "content": []},
            },
            {"type": "response.output_text.delta", "delta": "Hello"},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "id": "msg_4",
                    "content": [{"type": "output_text", "text": "Hello"}],
                },
            },
            {
                "type": "response.done",
                "response": {
                    "status": "completed",
                    "usage": {
                        "input_tokens": 2,
                        "output_tokens": 1,
                        "total_tokens": 3,
                        "input_tokens_details": {"cached_tokens": 0},
                    },
                },
            },
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(api_key=_build_fake_jwt("acc_test")),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert events[-1]["type"] == "done"
    assert events[-1]["message"].content[0].text == "Hello"
    assert events[-1]["message"].response_id == "resp_4"


def test_openai_codex_responses_stream_handles_function_call_events() -> None:
    client = _FakeCodexClient(
        events=[
            {"type": "response.created", "response": {"id": "resp_5"}},
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "calc",
                },
            },
            {"type": "response.function_call_arguments.delta", "delta": '{"x":1}'},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "calc",
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {
                        "input_tokens": 2,
                        "output_tokens": 1,
                        "total_tokens": 3,
                        "input_tokens_details": {"cached_tokens": 0},
                    },
                },
            },
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=True),
            {
                "messages": [
                    UserMessage(role="user", content="use a tool", timestamp=0.0)
                ]
            },
            OpenAICodexResponsesOptions(api_key=_build_fake_jwt("acc_test")),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert [event["type"] for event in events] == [
        "start",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_end",
        "done",
    ]
    tool_call = events[-1]["message"].content[0]
    assert tool_call.id == "call_1|fc_1"
    assert tool_call.name == "calc"
    assert tool_call.arguments == {"x": 1}


def test_openai_codex_responses_retries_retryable_sse_failure_through_runtime() -> None:
    client = _FakeCodexClient(
        stream_behaviors=[
            _FakeStreamBehavior(status_code=429, text="rate limited"),
            _FakeStreamBehavior(
                events=[
                    {"type": "response.created", "response": {"id": "resp_retry"}},
                    {
                        "type": "response.output_item.added",
                        "item": {"type": "message", "id": "msg_retry", "content": []},
                    },
                    {"type": "response.output_text.delta", "delta": "Hello"},
                    {
                        "type": "response.output_item.done",
                        "item": {
                            "type": "message",
                            "id": "msg_retry",
                            "content": [{"type": "output_text", "text": "Hello"}],
                        },
                    },
                    {"type": "response.completed", "response": {"status": "completed"}},
                ]
            ),
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(
                api_key=_build_fake_jwt("acc_test"),
                retry=RetryOptions(max_attempts=2, max_delay_seconds=0),
            ),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert client.stream_call_count == 2
    assert events[-1]["type"] == "done"
    assert events[-1]["message"].content[0].text == "Hello"


def test_openai_codex_responses_does_not_retry_inside_adapter() -> None:
    client = _FakeCodexClient(
        stream_behaviors=[
            _FakeStreamBehavior(status_code=429, text="rate limited"),
            _FakeStreamBehavior(
                events=[
                    {"type": "response.created", "response": {"id": "resp_retry"}},
                    {"type": "response.output_text.delta", "delta": "unexpected"},
                    {"type": "response.completed", "response": {"status": "completed"}},
                ]
            ),
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(
                api_key=_build_fake_jwt("acc_test"),
                retry=RetryOptions(max_attempts=1, max_delay_seconds=0),
            ),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert client.stream_call_count == 1
    assert events[-1]["type"] == "error"
    assert events[-1]["error_info"]["statusCode"] == 429


def test_openai_codex_responses_surfaces_http_error_code() -> None:
    client = _FakeCodexClient(
        stream_behaviors=[_FakeStreamBehavior(status_code=401, text="Unauthorized")]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(api_key=_build_fake_jwt("acc_test")),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == 401
    assert events[-1]["error"].error_message == "Unauthorized"


def test_openai_codex_responses_omits_non_http_error_code() -> None:
    client = _FakeCodexClient(
        stream_behaviors=[
            _FakeStreamBehavior(status_code=700, text="non-standard status")
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(api_key=_build_fake_jwt("acc_test")),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert events[-1]["type"] == "error"
    assert "code" not in events[-1]
    assert events[-1]["error"].error_message == "non-standard status"


def test_openai_codex_responses_surfaces_parsed_error_message() -> None:
    client = _FakeCodexClient(
        stream_behaviors=[
            _FakeStreamBehavior(
                status_code=400,
                text='{"error":{"type":"invalid_request_error","message":"Unsupported model for ChatGPT plan"}}',
            ),
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(api_key=_build_fake_jwt("acc_test"), retries=0),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert events[-1]["type"] == "error"
    assert events[-1]["error"].error_message == "Unsupported model for ChatGPT plan"


def test_openai_codex_responses_auto_transport_falls_back_to_sse_when_websocket_unavailable() -> (
    None
):
    client = _FakeCodexClient(
        websocket_error=RuntimeError(
            "WebSocket transport is not available in this runtime"
        ),
        events=[
            {"type": "response.created", "response": {"id": "resp_auto"}},
            {
                "type": "response.output_item.added",
                "item": {"type": "message", "id": "msg_auto", "content": []},
            },
            {"type": "response.output_text.delta", "delta": "Hello"},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "id": "msg_auto",
                    "content": [{"type": "output_text", "text": "Hello"}],
                },
            },
            {"type": "response.completed", "response": {"status": "completed"}},
        ],
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(
                api_key=_build_fake_jwt("acc_test"),
                transport="auto",
                session_id="sess_ws",
            ),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert client.websocket_connect_count == 1
    assert client.stream_call_count == 1
    assert events[-1]["type"] == "done"
    assert events[-1]["message"].response_id == "resp_auto"


def test_openai_codex_responses_websocket_transport_does_not_fallback_to_sse() -> None:
    client = _FakeCodexClient(
        websocket_error=RuntimeError("WebSocket closed 1011"),
        events=[
            {"type": "response.completed", "response": {"status": "completed"}},
        ],
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(
                api_key=_build_fake_jwt("acc_test"),
                transport="websocket",
                session_id="sess_ws",
            ),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert client.websocket_connect_count == 1
    assert client.stream_call_count == 0
    assert events[-1]["type"] == "error"
    assert events[-1]["error"].error_message == "WebSocket closed 1011"


def test_openai_codex_responses_websocket_uses_runtime_config_headers() -> None:
    client = _FakeCodexClient(
        websocket_batches=[
            [{"type": "response.completed", "response": {"status": "completed"}}]
        ]
    )
    get_default_model_registry().register_endpoint(
        "openai-codex",
        Endpoint(
            id="openai-codex-responses",
            provider="openai-codex",
            api="openai-codex-responses",
            compat=Compat.from_raw(
                {
                    "codexOriginator": "compat-ws",
                    "codexUserAgent": "compat-ws-agent",
                }
            ),
            models={
                "gpt-5.3-codex": Model(
                    id="gpt-5.3-codex",
                    provider="openai-codex",
                    endpoint="openai-codex-responses",
                )
            },
        ),
    )
    model = get_default_model_registry().get_model(
        "openai-codex",
        "openai-codex-responses",
        "gpt-5.3-codex",
    )
    provider = OpenAICodexResponsesProvider(client=client)

    async def _run() -> list[dict]:
        stream = await _stream(
            provider,
            model,
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(
                api_key=_build_fake_jwt("acc_test"),
                transport="websocket",
                session_id="sess_ws_config",
            ),
        )
        return await _collect_stream_events(stream)

    events = asyncio.run(_run())

    assert events[-1]["type"] == "done"
    assert client.last_headers["originator"] == "compat-ws"
    assert client.last_headers["User-Agent"] == "compat-ws-agent"


def test_openai_codex_responses_websocket_reuses_connection_for_same_session() -> None:
    client = _FakeCodexClient(
        websocket_batches=[
            [
                {"type": "response.created", "response": {"id": "resp_ws_1"}},
                {
                    "type": "response.output_item.added",
                    "item": {"type": "message", "id": "msg_ws_1", "content": []},
                },
                {"type": "response.output_text.delta", "delta": "One"},
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "message",
                        "id": "msg_ws_1",
                        "content": [{"type": "output_text", "text": "One"}],
                    },
                },
                {"type": "response.completed", "response": {"status": "completed"}},
            ],
            [
                {"type": "response.created", "response": {"id": "resp_ws_2"}},
                {
                    "type": "response.output_item.added",
                    "item": {"type": "message", "id": "msg_ws_2", "content": []},
                },
                {"type": "response.output_text.delta", "delta": "Two"},
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "message",
                        "id": "msg_ws_2",
                        "content": [{"type": "output_text", "text": "Two"}],
                    },
                },
                {"type": "response.completed", "response": {"status": "completed"}},
            ],
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    options = OpenAICodexResponsesOptions(
        api_key=_build_fake_jwt("acc_test"),
        transport="websocket",
        session_id="sess_reuse",
    )

    first_stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="one", timestamp=0.0)]},
            options,
        )
    )
    first_events = asyncio.run(_collect_stream_events(first_stream))

    second_stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="two", timestamp=0.0)]},
            options,
        )
    )
    second_events = asyncio.run(_collect_stream_events(second_stream))

    assert client.websocket_connect_count == 1
    assert first_events[-1]["message"].content[0].text == "One"
    assert second_events[-1]["message"].content[0].text == "Two"


def test_openai_codex_responses_websocket_close_before_completion_is_error() -> None:
    client = _FakeCodexClient(
        websocket_batches=[
            [
                {"type": "response.created", "response": {"id": "resp_ws_close"}},
                {
                    "type": "response.output_item.added",
                    "item": {"type": "message", "id": "msg_ws_close", "content": []},
                },
                {"type": "response.output_text.delta", "delta": "Partial"},
            ],
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client)
    stream = asyncio.run(
        _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            OpenAICodexResponsesOptions(
                api_key=_build_fake_jwt("acc_test"),
                transport="websocket",
                session_id="sess_close",
            ),
        )
    )

    events = asyncio.run(_collect_stream_events(stream))

    assert events[-1]["type"] == "error"
    assert (
        events[-1]["error"].error_message
        == "WebSocket stream closed before response.completed"
    )


def test_openai_codex_responses_websocket_idle_expiry_closes_and_evicts_cached_socket() -> (
    None
):
    client = _FakeCodexClient(
        websocket_batches=[
            [
                {"type": "response.created", "response": {"id": "resp_ws_idle_1"}},
                {
                    "type": "response.output_item.added",
                    "item": {"type": "message", "id": "msg_ws_idle_1", "content": []},
                },
                {"type": "response.output_text.delta", "delta": "One"},
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "message",
                        "id": "msg_ws_idle_1",
                        "content": [{"type": "output_text", "text": "One"}],
                    },
                },
                {"type": "response.completed", "response": {"status": "completed"}},
            ],
            [
                {"type": "response.created", "response": {"id": "resp_ws_idle_2"}},
                {
                    "type": "response.output_item.added",
                    "item": {"type": "message", "id": "msg_ws_idle_2", "content": []},
                },
                {"type": "response.output_text.delta", "delta": "Two"},
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "message",
                        "id": "msg_ws_idle_2",
                        "content": [{"type": "output_text", "text": "Two"}],
                    },
                },
                {"type": "response.completed", "response": {"status": "completed"}},
            ],
        ]
    )
    provider = OpenAICodexResponsesProvider(client=client, websocket_cache_ttl_ms=10)
    options = OpenAICodexResponsesOptions(
        api_key=_build_fake_jwt("acc_test"),
        transport="websocket",
        session_id="sess_idle",
    )

    async def _run() -> list[dict]:
        first_stream = await _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="one", timestamp=0.0)]},
            options,
        )
        await _collect_stream_events(first_stream)
        await asyncio.sleep(0.05)
        second_stream = await _stream(
            provider,
            _Model(reasoning=False),
            {"messages": [UserMessage(role="user", content="two", timestamp=0.0)]},
            options,
        )
        return await _collect_stream_events(second_stream)

    second_events = asyncio.run(_run())

    assert client.websocket_connect_count == 2
    assert second_events[-1]["message"].content[0].text == "Two"


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


async def _collect_stream_events(stream) -> list[dict]:
    return [event async for event in stream]


def _build_fake_jwt(account_id: str) -> str:
    import base64

    def _b64(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({"https://api.openai.com/auth": {"chatgpt_account_id": account_id}})
    return f"{header}.{payload}.sig"


class _FakeCodexClient:
    def __init__(
        self,
        *,
        events: list[dict] | None = None,
        stream_behaviors: list["_FakeStreamBehavior"] | None = None,
        websocket_events: list[dict] | None = None,
        websocket_batches: list[list[dict]] | None = None,
        websocket_error: Exception | None = None,
    ) -> None:
        self._events = events or []
        self._stream_behaviors = list(stream_behaviors or [])
        self._websocket_events = websocket_events or []
        self._websocket_batches = [list(batch) for batch in (websocket_batches or [])]
        self._websocket_error = websocket_error
        self.last_url: str | None = None
        self.last_headers: dict[str, str] | None = None
        self.last_json: dict | None = None
        self.stream_call_count = 0
        self.websocket_call_count = 0
        self.websocket_connect_count = 0

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict,
        timeout=None,
    ):
        assert method == "POST"
        self.stream_call_count += 1
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        if self._stream_behaviors:
            behavior = self._stream_behaviors.pop(0)
            return _FakeStreamContext(
                behavior.events, status_code=behavior.status_code, text=behavior.text
            )
        return _FakeStreamContext(self._events)

    async def websocket_stream(
        self, url: str, *, headers: dict[str, str], json: dict, timeout=None
    ):
        self.websocket_call_count += 1
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        if self._websocket_error is not None:
            raise self._websocket_error
        for event in self._websocket_events:
            yield event

    async def connect_websocket(
        self, url: str, *, headers: dict[str, str], timeout=None
    ):
        self.websocket_connect_count += 1
        self.last_url = url
        self.last_headers = headers
        if self._websocket_error is not None:
            raise self._websocket_error
        return _FakeWebSocket(self._websocket_batches)


@dataclass(frozen=True)
class _FakeStreamBehavior:
    events: list[dict] = field(default_factory=list)
    status_code: int = 200
    text: str = ""


class _FakeStreamContext:
    def __init__(
        self, events: list[dict], *, status_code: int = 200, text: str = ""
    ) -> None:
        self._events = events
        self._status_code = status_code
        self._text = text

    async def __aenter__(self):
        return _FakeResponse(
            self._events, status_code=self._status_code, text=self._text
        )

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeResponse:
    def __init__(
        self, events: list[dict], *, status_code: int = 200, text: str = ""
    ) -> None:
        self.status_code = status_code
        self._text = text
        self._lines: list[str] = []
        for event in events:
            self._lines.append(f"data: {json.dumps(event)}")
            self._lines.append("")

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def atext(self) -> str:
        return self._text


class _FakeWebSocket:
    def __init__(self, batches: list[list[dict]]) -> None:
        self._batches = batches
        self.sent_payloads: list[dict] = []
        self.closed = False

    async def send(self, payload: dict) -> None:
        self.sent_payloads.append(payload)

    async def events(self):
        if not self._batches:
            return
        for event in self._batches.pop(0):
            yield event

    async def close(self, code: int = 1000, reason: str = "done") -> None:
        self.closed = True


@dataclass(frozen=True)
class _Model:
    id: str = "gpt-5.3-codex"
    base_url: str | None = None
    reasoning: bool = False
    input: tuple[str, ...] = ("text", "image")
    max_tokens: int | None = 4096
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, object] = field(
        default_factory=lambda: {
            "codexIncludeClientRequestId": True,
            "codexIncludeConversationId": False,
            "codexPromptCacheRetention": "in-memory",
            "codexOriginator": "loushang",
            "codexUserAgent": "loushang",
        }
    )
    defaults: dict[str, object] = field(default_factory=dict)
    provider_id: str = "openai-codex"
    endpoint_id: str = "openai-codex-responses"


@pytest.fixture(autouse=True)
def _default_registry() -> None:
    clear_default_model_registry()
    registry = get_default_model_registry()
    registry.register_endpoint(
        "openai-codex",
        Endpoint(
            id="openai-codex-responses",
            provider="openai-codex",
            api="openai-codex-responses",
            compat=Compat.from_raw(
                {
                    "codexIncludeClientRequestId": True,
                    "codexIncludeConversationId": False,
                    "codexPromptCacheRetention": "in-memory",
                    "codexOriginator": "loushang",
                    "codexUserAgent": "loushang",
                }
            ),
            models={
                "gpt-5.3-codex": Model(
                    id="gpt-5.3-codex",
                    provider="openai-codex",
                    endpoint="openai-codex-responses",
                )
            },
        ),
    )
