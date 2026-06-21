from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai.api.streaming import stream, stream_simple
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.context import NORMALIZED_CONTEXT_MARKER
from loushang.ai.model import (
    Capabilities,
    EndpointProtocolFeatures,
    EndpointWireDialect,
)
from loushang.ai.options import ModelCallOptions, OpenAICompletionsOptions
from loushang.ai.provider import ResolvedRequest
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.types import (
    AssistantMessage,
    ImagePart,
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

    async def stream(self, model, context, options, request):
        self.context = context
        self.options = options
        self.request = request
        return _DoneStream()

    async def stream_simple(self, model, context, options, request):
        return await self.stream(model, context, options, request)


class _LegacyProvider:
    api = "faux"

    def __init__(self, api: str = "faux") -> None:
        self.api = api
        self.context = None
        self.options = None

    async def stream(self, model, context, options):
        self.context = context
        self.options = options
        return _DoneStream()

    async def stream_simple(self, model, context, options):
        return await self.stream(model, context, options)


class _LegacyProviderWithOptionalDebug:
    api = "faux"

    def __init__(self, api: str = "faux") -> None:
        self.api = api
        self.context = None
        self.debug = None

    async def stream(self, model, context, options, debug=False):
        self.context = context
        self.debug = debug
        return _DoneStream()

    async def stream_simple(self, model, context, options, debug=False):
        return await self.stream(model, context, options, debug)


class _KeywordRequestProvider:
    api = "faux"

    def __init__(self, api: str = "faux") -> None:
        self.api = api
        self.context = None
        self.options = None
        self.request = None

    async def stream(self, model, context, options, *, request=None):
        self.context = context
        self.options = options
        self.request = request
        return _DoneStream()

    async def stream_simple(self, model, context, options, *, request=None):
        return await self.stream(model, context, options, request=request)


class _DoneStream:
    def __aiter__(self):
        async def _iterate():
            if False:
                yield None

        return _iterate()

    async def result(self):
        return None


def test_stream_exposes_pairing_mode_through_public_options(
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

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert provider.context["messages"][0].role == "user"


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

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert provider.request.api == "faux"


def test_stream_supports_legacy_registered_provider_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _LegacyProvider()
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

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert provider.context["messages"][0].role == "user"


def test_stream_supports_keyword_request_registered_provider_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _KeywordRequestProvider()
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

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert provider.request.api == "faux"


def test_stream_simple_supports_keyword_request_registered_provider_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _KeywordRequestProvider()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)

    asyncio.run(
        stream_simple(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
            registry=registry,
        )
    )

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert provider.request.api == "faux"


def test_stream_supports_legacy_provider_from_custom_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _LegacyProvider()
    registry = _Registry(provider)

    asyncio.run(
        stream(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
            registry=registry,
        )
    )

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert provider.context["messages"][0].role == "user"


def test_stream_simple_supports_legacy_provider_from_custom_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _LegacyProvider()
    registry = _Registry(provider)

    asyncio.run(
        stream_simple(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
            registry=registry,
        )
    )

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert provider.context["messages"][0].role == "user"


def test_get_api_provider_stream_supports_previous_wrapper_signature(
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


def test_get_api_provider_stream_supports_previous_legacy_provider_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _LegacyProvider()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)

    asyncio.run(
        registry.get_api_provider("faux").stream(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
        )
    )

    assert provider.context["messages"][0].role == "user"


def test_get_api_provider_stream_does_not_treat_legacy_optional_arg_as_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch)
    provider = _LegacyProviderWithOptionalDebug()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)

    asyncio.run(
        registry.get_api_provider("faux").stream(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            ModelCallOptions(),
        )
    )

    assert provider.context["messages"][0].role == "user"
    assert provider.debug is False


def test_get_api_provider_stream_rejects_mismatched_resolved_request() -> None:
    provider = _Provider()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    request = SimpleNamespace(api="other", capabilities=Capabilities(input=("text",)))

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
    request = SimpleNamespace(
        api="anthropic-messages",
        provider="anthropic",
        capabilities=Capabilities(input=("text",)),
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
    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert normalized_assistant.content[0].id == "call_1"
    assert normalized_tool_result.tool_call_id == "call_1"


def test_stream_validates_resolved_request_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolved_request(monkeypatch, capabilities=Capabilities(input=("text",)))
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
        capabilities=Capabilities(input=("text", "image")),
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

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True


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
        capabilities=Capabilities(input=("text",), tool_use=True, max_tokens=4096),
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
                    Tool(
                        name="calc",
                        description="Calculate values",
                        parameters={"type": "object"},
                    )
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
            capabilities=capabilities or Capabilities(input=("text",)),
        )

    def _resolve_provider_request(provider_api, _model, *, options=None, request=None):
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
    module = ModuleType("openai")
    module.AsyncOpenAI = _FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)


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
