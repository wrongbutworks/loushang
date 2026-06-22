from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai.advanced import OpenAICompletionsOptions, OpenAIResponsesOptions
from loushang.ai.api.streaming import complete, stream, stream_simple
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.context import (
    NORMALIZED_CONTEXT_MARKER,
    NormalizedContext,
)
from loushang.ai.errors import AIRateLimitError
from loushang.ai.model import (
    Capabilities,
    EndpointProtocolFeatures,
    EndpointWireDialect,
)
from loushang.ai.options import (
    CallOptions,
    ModelCallOptions,
    ReasoningOptions,
    SimpleCallOptions,
)
from loushang.ai.provider import ResolvedRequest
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.providers.openai_responses import OpenAIResponsesProvider
from loushang.ai.types import (
    AssistantMessage,
    ImagePart,
    TextPart,
    Tool,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)


@dataclass
class _Capabilities:
    supports_image_input: bool = False
    supports_thinking: bool = False


@dataclass
class _Model:
    id: str = "test-model"
    api: str | None = None
    capabilities: _Capabilities = field(default_factory=_Capabilities)


class _Registry:
    def __init__(self, provider) -> None:
        self._provider = provider

    def get_api_provider(self, _api: str):
        return self._provider


class _Provider:
    api = "faux"

    def __init__(self, api: str = "faux") -> None:
        self.api = api
        self.context = None
        self.options = None
        self.request = None

    async def stream_raw(self, request):
        self.context = request.context
        self.options = request.options
        self.request = request.resolved
        yield {"type": "response_done"}


class _ErrorProvider(_Provider):
    async def stream_raw(self, request):
        self.context = request.context
        self.options = request.options
        self.request = request.resolved
        yield {
            "type": "response_error",
            "message": "rate limited",
            "code": 429,
            "error_info": {
                "code": "rate_limit",
                "message": "rate limited",
                "source": "faux",
                "retryable": True,
                "provider": "faux",
                "endpoint": None,
                "model": "test-model",
                "statusCode": 429,
                "requestId": "req_public",
                "details": {},
            },
        }


def _assert_normalized_provider_context(context: object) -> NormalizedContext:
    assert isinstance(context, NormalizedContext)
    assert NORMALIZED_CONTEXT_MARKER not in context
    return context


class _LegacyProvider:
    api = "faux"

    def __init__(self, api: str = "faux") -> None:
        self.api = api
        self.context = None
        self.options = None

    async def stream_raw(self, model, context, options):
        self.context = context
        self.options = options
        yield {"type": "response_done"}


class _LegacyProviderWithOptionalDebug:
    api = "faux"

    def __init__(self, api: str = "faux") -> None:
        self.api = api
        self.context = None
        self.debug = None

    async def stream_raw(self, model, context, options, debug=False):
        self.context = context
        self.debug = debug
        yield {"type": "response_done"}


class _KeywordRequestProvider:
    api = "faux"

    def __init__(self, api: str = "faux") -> None:
        self.api = api
        self.context = None
        self.options = None
        self.request = None

    async def stream_raw(self, model, context, options, *, request=None):
        self.context = context
        self.options = options
        self.request = request
        yield {"type": "response_done"}


class _StreamOnlyProvider:
    api = "faux"

    async def stream(self, model, context, options, request):
        return None


def test_stream_defaults_to_strict_pairing_and_exposes_repair_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)
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
    )

    with pytest.raises(ValueError, match="Missing tool results before next message"):
        asyncio.run(
            stream(
                _Model(),
                {
                    "messages": [
                        assistant,
                        UserMessage(role="user", content="next", timestamp=0.0),
                    ]
                },
                ModelCallOptions(),
                registry=registry,
            )
        )

    asyncio.run(
        stream(
            _Model(),
            {
                "messages": [
                    assistant,
                    UserMessage(role="user", content="next", timestamp=0.0),
                ]
            },
            ModelCallOptions(pairing_mode="repair"),
            registry=registry,
        )
    )

    normalized = _assert_normalized_provider_context(provider.context)
    assert [
        type(message).__name__
        for message in normalized.messages
    ] == [
        "AssistantMessage",
        "ToolResultMessage",
        "UserMessage",
    ]
    synthetic = normalized.messages[1]
    assert isinstance(synthetic, ToolResultMessage)
    assert synthetic.tool_call_id == "call_1"
    assert synthetic.is_error is True


def test_complete_raises_typed_error_for_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _ErrorProvider()
    registry = _Registry(provider)

    with pytest.raises(AIRateLimitError) as exc_info:
        asyncio.run(
            complete(
                _Model(),
                {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
                CallOptions(),
                registry=registry,
            )
        )

    assert exc_info.value.info.status_code == 429
    assert exc_info.value.info.request_id == "req_public"


def test_stream_exposes_strict_pairing_through_public_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)
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
    )

    with pytest.raises(ValueError, match="Missing tool results before next message"):
        asyncio.run(
            stream(
                _Model(),
                {
                    "messages": [
                        assistant,
                        UserMessage(role="user", content="next", timestamp=0.0),
                    ]
                },
                ModelCallOptions(pairing_mode="strict"),
                registry=registry,
            )
        )


def test_stream_passes_normalized_context_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)

    asyncio.run(
        stream(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
            registry=registry,
        )
    )

    normalized = _assert_normalized_provider_context(provider.context)
    assert normalized["messages"][0].role == "user"


@pytest.mark.parametrize(
    ("capabilities", "context", "options", "expected_message"),
    [
        (
            Capabilities(input=("text",), stream=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
            "does not support streaming",
        ),
        (
            Capabilities(input=("text",), stream=True, tool_use=False),
            {
                "messages": [UserMessage(role="user", content="hello", timestamp=0.0)],
                "tools": [
                    {
                        "name": "calc",
                        "description": "Calculate values",
                        "parameters": {"type": "object"},
                    }
                ],
            },
            ModelCallOptions(),
            "does not support tool use",
        ),
        (
            Capabilities(input=("text",), stream=True, reasoning=False),
            {"messages": [], "emit_thinking": True},
            ModelCallOptions(),
            "does not support reasoning",
        ),
        (
            Capabilities(input=("text",), stream=True, reasoning=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            CallOptions(reasoning=ReasoningOptions(effort="high")),
            "does not support reasoning",
        ),
        (
            Capabilities(input=("text",), stream=True, structured_output=False),
            {
                "messages": [UserMessage(role="user", content="hello", timestamp=0.0)],
                "response_format": {"type": "json_schema"},
            },
            ModelCallOptions(),
            "does not support structured output",
        ),
        (
            Capabilities(input=("text",), stream=True, temperature=False),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(temperature=0.2),
            "does not support temperature",
        ),
        (
            Capabilities(input=("text",), stream=True),
            {
                "messages": [
                    UserMessage(
                        role="user",
                        content=[
                            ImagePart(
                                type="image",
                                data="aGVsbG8=",
                                mime_type="image/png",
                            )
                        ],
                        timestamp=0.0,
                    )
                ]
            },
            ModelCallOptions(),
            "does not support image input",
        ),
        (
            Capabilities(input=("text",), stream=True, attachment=False),
            {
                "messages": [UserMessage(role="user", content="hello", timestamp=0.0)],
                "attachments": [{"id": "file_1"}],
            },
            ModelCallOptions(),
            "does not support attachment",
        ),
    ],
)
def test_stream_enforces_capability_matrix(
    monkeypatch: pytest.MonkeyPatch,
    capabilities: Capabilities,
    context: dict[str, object],
    options: ModelCallOptions,
    expected_message: str,
) -> None:
    _patch_resolved_request(monkeypatch, capabilities=capabilities)
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)

    with pytest.raises(ValueError, match=expected_message):
        asyncio.run(stream(_Model(), context, options, registry=registry))

    assert provider.context is None


def test_stream_allows_complete_capability_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(
        monkeypatch,
        capabilities=Capabilities(
            input=("text", "image"),
            stream=True,
            tool_use=True,
            reasoning=True,
            structured_output=True,
            attachment=True,
            temperature=True,
        ),
    )
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)

    asyncio.run(
        stream(
            _Model(),
            {
                "messages": [
                    UserMessage(
                        role="user",
                        content=[
                            ImagePart(
                                type="image",
                                data="aGVsbG8=",
                                mime_type="image/png",
                            )
                        ],
                        timestamp=0.0,
                    )
                ],
                "tools": [
                    {
                        "name": "calc",
                        "description": "Calculate values",
                        "parameters": {"type": "object"},
                    }
                ],
                "emit_thinking": True,
                "response_format": {"type": "json_schema"},
                "attachments": [{"id": "file_1"}],
            },
            ModelCallOptions(temperature=0.2),
            registry=registry,
        )
    )

    normalized = _assert_normalized_provider_context(provider.context)
    assert normalized.tools is not None
    assert normalized["emit_thinking"] is True
    assert normalized["response_format"] == {"type": "json_schema"}
    assert normalized["attachments"] == [{"id": "file_1"}]


def test_complete_does_not_require_stream_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(
        monkeypatch,
        capabilities=Capabilities(input=("text",), stream=False),
    )
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)

    result = asyncio.run(
        complete(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
            registry=registry,
        )
    )

    assert result.api == "faux"
    assert result.provider == "faux"
    assert result.model == "test-model"
    _assert_normalized_provider_context(provider.context)


def test_stream_canonicalizes_raw_dict_context_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(
        monkeypatch, capabilities=Capabilities(input=("text", "image"), stream=True)
    )
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)

    asyncio.run(
        stream(
            _Model(),
            {
                "systemPrompt": "system text",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "hello"},
                            {
                                "type": "image",
                                "data": "aW1n",
                                "mimeType": "image/png",
                            },
                        ],
                        "timestamp": 12.0,
                    }
                ],
            },
            ModelCallOptions(),
            registry=registry,
        )
    )

    normalized = _assert_normalized_provider_context(provider.context)
    message = normalized["messages"][0]
    assert normalized.system_prompt == "system text"
    assert isinstance(message, UserMessage)
    assert message.content == [
        TextPart(type="text", text="hello"),
        ImagePart(type="image", data="aW1n", mime_type="image/png"),
    ]
    assert message.timestamp == 12.0


def test_stream_rejects_raw_dict_tools_with_non_object_parameters_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _Provider()
    registry = _Registry(provider)

    with pytest.raises(TypeError, match="Unsupported tool parameters type"):
        asyncio.run(
            stream(
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                    "tools": [
                        {
                            "name": "calc",
                            "description": "Calculate values",
                            "parameters": "bad",
                        }
                    ],
                },
                ModelCallOptions(),
                registry=registry,
            )
        )

    assert provider.context is None


def test_stream_rejects_raw_dict_tools_with_invalid_names_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _Provider()
    registry = _Registry(provider)

    with pytest.raises(TypeError, match="Unsupported tool name type"):
        asyncio.run(
            stream(
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                    "tools": [
                        {
                            "name": "",
                            "description": "bad",
                            "parameters": {"type": "object"},
                        }
                    ],
                },
                ModelCallOptions(),
                registry=registry,
            )
        )

    assert provider.context is None


def test_stream_passes_request_through_registered_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)

    asyncio.run(
        stream(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
            registry=registry,
        )
    )

    _assert_normalized_provider_context(provider.context)
    assert provider.request.api == "faux"


def test_register_api_provider_rejects_stream_only_provider() -> None:
    registry = ApiProviderRegistry()

    with pytest.raises(TypeError, match="stream_raw"):
        registry.register_api_provider(_StreamOnlyProvider())


def test_register_api_provider_rejects_legacy_provider_signature() -> None:
    provider = _LegacyProvider()
    registry = ApiProviderRegistry()

    with pytest.raises(TypeError, match="exactly one ProviderRequest"):
        registry.register_api_provider(provider)


def test_register_api_provider_rejects_keyword_request_signature() -> None:
    provider = _KeywordRequestProvider()
    registry = ApiProviderRegistry()

    with pytest.raises(TypeError, match="exactly one ProviderRequest"):
        registry.register_api_provider(provider)


def test_register_api_provider_rejects_optional_legacy_argument_signature() -> None:
    provider = _LegacyProviderWithOptionalDebug()
    registry = ApiProviderRegistry()

    with pytest.raises(TypeError, match="exactly one ProviderRequest"):
        registry.register_api_provider(provider)


@pytest.mark.parametrize(
    "api",
    (
        "openai-completions",
        "openai-responses",
        "anthropic-messages",
        "openai-codex-responses",
    ),
)
def test_stream_simple_maps_reasoning_options_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    api: str,
) -> None:
    _patch_resolved_request(
        monkeypatch,
        capabilities=Capabilities(input=("text",), stream=True, reasoning=True),
        api=api,
        provider="custom",
    )
    provider = _Provider(api=api)
    registry = _Registry(provider)

    asyncio.run(
        stream_simple(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            SimpleCallOptions(
                reasoning="medium",
                thinking_budgets={"medium": 2048},
                max_output_tokens=123,
            ),
            registry=registry,
        )
    )

    assert isinstance(provider.options, CallOptions)
    assert not isinstance(provider.options, SimpleCallOptions)
    assert provider.options.max_output_tokens == 123
    assert provider.options.reasoning == ReasoningOptions(
        enabled=True,
        effort="medium",
        budget_tokens=2048,
        expose_summary=True,
    )
    assert provider.request.api == api


def test_stream_rejects_legacy_provider_from_custom_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _LegacyProvider()
    registry = _Registry(provider)

    with pytest.raises(TypeError, match="exactly one ProviderRequest"):
        asyncio.run(
            stream(
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                ModelCallOptions(),
                registry=registry,
            )
        )


def test_stream_simple_rejects_legacy_provider_from_custom_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _LegacyProvider()
    registry = _Registry(provider)

    with pytest.raises(TypeError, match="exactly one ProviderRequest"):
        asyncio.run(
            stream_simple(
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                SimpleCallOptions(),
                registry=registry,
            )
        )


def test_get_api_provider_stream_supports_wrapper_signature_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _Provider()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)

    asyncio.run(
        registry.get_api_provider("faux").stream(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
        )
    )

    assert provider.request.api == "faux"
    assert provider.context["messages"][0].role == "user"


def test_get_api_provider_stream_rejects_legacy_provider_signature() -> None:
    provider = _LegacyProvider()
    registry = ApiProviderRegistry()

    with pytest.raises(TypeError, match="exactly one ProviderRequest"):
        registry.register_api_provider(provider)


def test_get_api_provider_stream_rejects_legacy_optional_arg_signature() -> None:
    provider = _LegacyProviderWithOptionalDebug()
    registry = ApiProviderRegistry()

    with pytest.raises(TypeError, match="exactly one ProviderRequest"):
        registry.register_api_provider(provider)

def test_get_api_provider_stream_rejects_mismatched_resolved_request() -> None:
    provider = _Provider()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    request = ResolvedRequest(
        provider="faux",
        endpoint="other",
        api="other",
        base_url=None,
        capabilities=Capabilities(input=("text",), stream=True),
    )

    with pytest.raises(ValueError, match="Mismatched api"):
        asyncio.run(
            registry.get_api_provider("faux").stream(
                _Model(),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                ModelCallOptions(),
                request,
            )
        )


def test_get_api_provider_stream_normalizes_context_against_resolved_request_api() -> (
    None
):
    provider = _Provider(api="anthropic-messages")
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    request = ResolvedRequest(
        api="anthropic-messages",
        provider="anthropic",
        endpoint="anthropic-messages",
        base_url=None,
        capabilities=Capabilities(input=("text",), stream=True),
    )
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call.1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
        provider="openai",
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
    )

    asyncio.run(
        registry.get_api_provider("anthropic-messages").stream(
            _Model(api="openai-responses"),
            {
                "messages": [
                    assistant,
                    ToolResultMessage(
                        role="toolResult",
                        tool_call_id="call.1",
                        tool_name="calc",
                        content=[],
                        is_error=False,
                        timestamp=0.0,
                    ),
                ]
            },
            ModelCallOptions(),
            request,
        )
    )

    normalized_assistant = provider.context["messages"][0]
    normalized_tool_result = provider.context["messages"][1]
    _assert_normalized_provider_context(provider.context)
    assert normalized_assistant.content[0].id == "call_1"
    assert normalized_tool_result.tool_call_id == "call_1"


def test_stream_validates_resolved_request_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(
        monkeypatch, capabilities=Capabilities(input=("text",), stream=True)
    )
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)

    with pytest.raises(ValueError, match="does not support image input"):
        asyncio.run(
            stream(
                _Model(capabilities=_Capabilities(supports_image_input=True)),
                {
                    "messages": [
                        UserMessage(
                            role="user",
                            content=[
                                ImagePart(
                                    type="image",
                                    data="aGVsbG8=",
                                    mime_type="image/png",
                                )
                            ],
                            timestamp=0.0,
                        )
                    ]
                },
                ModelCallOptions(),
                registry=registry,
            )
        )


def test_stream_allows_capabilities_after_request_resolution_switches_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(
        monkeypatch,
        capabilities=Capabilities(input=("text", "image"), stream=True),
    )
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)

    asyncio.run(
        stream(
            _Model(capabilities=_Capabilities(supports_image_input=False)),
            {
                "messages": [
                    UserMessage(
                        role="user",
                        content=[
                            ImagePart(
                                type="image",
                                data="aGVsbG8=",
                                mime_type="image/png",
                            )
                        ],
                        timestamp=0.0,
                    )
                ]
            },
            ModelCallOptions(),
            registry=registry,
        )
    )

    _assert_normalized_provider_context(provider.context)


def test_stream_normalizes_context_against_resolved_request_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(
        monkeypatch,
        api="anthropic-messages",
        provider="anthropic",
    )
    provider = _Provider(api="anthropic-messages")
    registry = _Registry(provider)
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call.1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
        provider="openai",
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
    )

    asyncio.run(
        stream(
            _Model(api="openai-responses"),
            {
                "messages": [
                    assistant,
                    ToolResultMessage(
                        role="toolResult",
                        tool_call_id="call.1",
                        tool_name="calc",
                        content=[],
                        is_error=False,
                        timestamp=0.0,
                    ),
                ]
            },
            ModelCallOptions(),
            registry=registry,
        )
    )

    normalized_assistant = provider.context["messages"][0]
    normalized_tool_result = provider.context["messages"][1]
    assert normalized_assistant.content[0].id == "call_1"
    assert normalized_tool_result.tool_call_id == "call_1"


def test_stream_public_path_uses_openai_completions_typed_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    registry = ApiProviderRegistry()
    registry.register_api_provider(OpenAICompletionsProvider())
    model = SimpleNamespace(
        id="gpt-test",
        provider_id="custom",
        endpoint_id="openai-completions",
        input=("text",),
        pricing=None,
    )
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        protocol=EndpointProtocolFeatures.from_raw(
            {"cache": {"promptKey": "supported"}}
        ),
        dialect=EndpointWireDialect.from_raw(
            {
                "maxOutputTokensField": "max_completion_tokens",
                "tools": {"streamFlag": True},
            }
        ),
        max_tokens=128,
        capabilities=Capabilities(
            input=("text",), stream=True, tool_use=True, max_tokens=4096
        ),
    )

    def _resolve_request(_model, options=None):
        return request

    monkeypatch.setattr(
        "loushang.ai.api.streaming.resolve_request_for_model",
        _resolve_request,
    )

    async def _run() -> None:
        event_stream = await stream(
            model,
            {
                "messages": [UserMessage(role="user", content="hello", timestamp=0.0)],
                "tools": [
                    {
                        "name": "calc",
                        "description": "Calculate values",
                        "parameters": {"type": "object"},
                    }
                ],
            },
            OpenAICompletionsOptions(
                cache_retention="short",
                session_id="session-public",
            ),
            registry=registry,
        )
        await event_stream.result()

    asyncio.run(_run())

    assert _FakeAsyncOpenAI.last_create_kwargs["max_completion_tokens"] == 128
    assert "max_tokens" not in _FakeAsyncOpenAI.last_create_kwargs
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == "session-public"
    assert _FakeAsyncOpenAI.last_create_kwargs["tool_stream"] is True
    assert _FakeAsyncOpenAI.last_create_kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "calc",
                "description": "Calculate values",
                "parameters": {"type": "object"},
            },
        }
    ]


def test_stream_public_path_uses_openai_responses_typed_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    registry = ApiProviderRegistry()
    registry.register_api_provider(OpenAIResponsesProvider())
    model = SimpleNamespace(
        id="gpt-test",
        api="anthropic-messages",
        provider_id="custom",
        endpoint_id="openai-responses",
        input=("text",),
        pricing=None,
    )
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-responses",
        api="openai-responses",
        base_url="https://api.openai.test/v1",
        headers={"Authorization": "Bearer test-key"},
        protocol=EndpointProtocolFeatures.from_raw(
            {
                "roles": {"developer": "unsupported"},
                "cache": {"longRetention": "unsupported"},
                "session": {"idHeader": "unsupported"},
            }
        ),
        dialect=EndpointWireDialect.from_raw(
            {"tools": {"assistantBridgeRequired": True}}
        ),
        max_tokens=128,
        capabilities=Capabilities(
            input=("text",),
            stream=True,
            tool_use=True,
            reasoning=True,
            max_tokens=4096,
        ),
    )

    def _resolve_request(_model, options=None):
        return request

    monkeypatch.setattr(
        "loushang.ai.api.streaming.resolve_request_for_model",
        _resolve_request,
    )

    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
        provider="custom",
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

    async def _run() -> None:
        event_stream = await stream(
            model,
            {
                "system_prompt": "Use system instructions.",
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
                    )
                ],
            },
            OpenAIResponsesOptions(
                cache_retention="long",
                session_id="session-responses",
            ),
            registry=registry,
        )
        await event_stream.result()

    asyncio.run(_run())

    assert _FakeAsyncOpenAI.last_create_kwargs["max_output_tokens"] == 128
    assert _FakeAsyncOpenAI.last_create_kwargs["input"] == [
        {"role": "system", "content": "Use system instructions."},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "calc",
            "arguments": '{"x": 1}',
        },
        {"type": "function_call_output", "call_id": "call_1", "output": "42"},
        {"role": "assistant", "content": "I have processed the tool results."},
        {"role": "user", "content": [{"type": "input_text", "text": "next"}]},
    ]
    assert _FakeAsyncOpenAI.last_create_kwargs["tools"] == [
        {
            "type": "function",
            "name": "calc",
            "description": "Calculate values",
            "parameters": {"type": "object"},
        }
    ]
    assert _FakeAsyncOpenAI.last_create_kwargs["prompt_cache_key"] == (
        "session-responses"
    )
    assert "prompt_cache_retention" not in _FakeAsyncOpenAI.last_create_kwargs
    assert "session_id" not in _FakeAsyncOpenAI.last_init_kwargs["default_headers"]


def _patch_resolved_request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    capabilities: Capabilities | None = None,
    api: str = "faux",
    provider: str = "faux",
) -> None:
    def _resolve_request(_model, options=None):
        return SimpleNamespace(
            api=api,
            provider=provider,
            capabilities=capabilities or Capabilities(input=("text",), stream=True),
        )

    def _resolve_provider_request(
        provider_api,
        _model,
        *,
        options=None,
        request=None,
        adapter_config_resolver=None,
    ):
        resolved = request if request is not None else _resolve_request(_model, options)
        if resolved.api != provider_api:
            raise ValueError(
                f"Mismatched api: provider={provider_api!r} request.api={resolved.api!r}"
            )
        return resolved

    monkeypatch.setattr(
        "loushang.ai.api.streaming.resolve_request_for_model",
        _resolve_request,
    )
    monkeypatch.setattr(
        "loushang.ai.provider.invocation.resolve_provider_request",
        _resolve_provider_request,
    )


def _fake_openai_module(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAsyncOpenAI.last_init_kwargs = {}
    _FakeAsyncOpenAI.last_create_kwargs = {}
    _FakeAsyncOpenAI.chunks = []
    _FakeAsyncOpenAI.events = [
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
        )
    ]
    module = ModuleType("openai")
    module.AsyncOpenAI = _FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)


class _FakeAsyncOpenAI:
    last_init_kwargs: dict[str, object] = {}
    last_create_kwargs: dict[str, object] = {}
    chunks: list[object] = []
    events: list[object] = []

    def __init__(self, **kwargs) -> None:
        type(self).last_init_kwargs = kwargs
        self.chat = SimpleNamespace(completions=_FakeCompletions(type(self)))
        self.responses = _FakeResponses(type(self))


class _FakeCompletions:
    def __init__(self, owner: type[_FakeAsyncOpenAI]) -> None:
        self._owner = owner

    async def create(self, **kwargs):
        self._owner.last_create_kwargs = kwargs
        return _FakeStream(self._owner.chunks)


class _FakeResponses:
    def __init__(self, owner: type[_FakeAsyncOpenAI]) -> None:
        self._owner = owner

    async def create(self, **kwargs):
        self._owner.last_create_kwargs = kwargs
        return _FakeStream(self._owner.events)


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
