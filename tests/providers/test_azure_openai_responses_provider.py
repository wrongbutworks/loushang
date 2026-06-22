from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai.context import normalize_context
from loushang.ai.model import (
    Auth,
    Capabilities,
    Endpoint,
    Model,
    ModelRegistry,
    Provider,
)
from loushang.ai.model.registry import (
    clear_default_model_registry,
    get_default_model_registry,
)
from loushang.ai.options import AzureOpenAIResponsesOptions
from loushang.ai.provider import ResolvedRequest
from loushang.ai.providers.azure_openai_responses import AzureOpenAIResponsesProvider
from loushang.ai.types import (
    AssistantMessage,
    Context,
    ImagePart,
    TextPart,
    Tool,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)


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
    return await provider.stream(
        model,
        _normalized_context(model, context, options),
        options,
        request,
    )


def test_azure_openai_responses_uses_azure_client_and_deployment_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME_MAP", "gpt-4o-mini=dep-mini")
    _patch_resolved_request(monkeypatch)
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(id="gpt-4o-mini"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AzureOpenAIResponsesOptions(
                    api_key="test-key",
                    azure_base_url="https://example.openai.azure.com/openai/v1",
                    azure_api_version="2025-04-01-preview",
                ),
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_init_kwargs == {
        "api_key": "test-key",
        "azure_endpoint": "https://example.openai.azure.com/openai/v1",
        "api_version": "2025-04-01-preview",
    }
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["model"] == "dep-mini"
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "hello"}]}
    ]


def test_azure_openai_responses_maps_tools_from_normalized_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch)
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(id="gpt-4o-mini"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ],
                    "tools": [
                        Tool(
                            name="calc",
                            description="Calculate values",
                            parameters={
                                "type": "object",
                                "properties": {"x": {"type": "number"}},
                                "required": ["x"],
                            },
                        )
                    ],
                },
                AzureOpenAIResponsesOptions(
                    api_key="test-key",
                    azure_base_url="https://example.openai.azure.com/openai/v1",
                ),
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_create_kwargs["tools"] == [
        {
            "type": "function",
            "name": "calc",
            "description": "Calculate values",
            "parameters": {
                "type": "object",
                "properties": {"x": {"type": "number"}},
                "required": ["x"],
            },
        }
    ]
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["tool_choice"] == "auto"


def test_azure_openai_responses_maps_upstream_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    monkeypatch.setenv(
        "AZURE_OPENAI_DEPLOYMENT_NAME_MAP", "vendor/gpt-4o-mini=dep-upstream"
    )
    _patch_resolved_request(monkeypatch, upstream_model_id="vendor/gpt-4o-mini")
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(id="gpt-4o-mini_public"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AzureOpenAIResponsesOptions(
                    api_key="test-key",
                    azure_base_url="https://example.openai.azure.com/openai/v1",
                ),
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_create_kwargs["model"] == "dep-upstream"


def test_azure_openai_responses_falls_back_to_upstream_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(monkeypatch, upstream_model_id="vendor/gpt-4o-mini")
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(id="gpt-4o-mini_public"),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AzureOpenAIResponsesOptions(
                    api_key="test-key",
                    azure_base_url="https://example.openai.azure.com/openai/v1",
                ),
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_create_kwargs["model"] == "vendor/gpt-4o-mini"


def test_azure_openai_responses_uses_resolved_capability_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    _patch_resolved_request(
        monkeypatch,
        max_tokens=None,
        capabilities=Capabilities(max_tokens=2048),
    )
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(max_tokens=1024),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                AzureOpenAIResponsesOptions(
                    api_key="test-key",
                    azure_base_url="https://example.openai.azure.com/openai/v1",
                ),
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_create_kwargs["max_output_tokens"] == 2048


def test_azure_openai_responses_supplied_compat_projects_to_typed_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    request = ResolvedRequest(
        provider="azure-openai",
        endpoint="azure-openai-responses",
        api="azure-openai-responses",
        base_url="https://example.openai.azure.com/openai/v1",
        headers={"Authorization": "Bearer test-key"},
        compat={
            "supportsDeveloperRole": False,
            "requiresAssistantAfterToolResult": True,
        },
        max_tokens=128,
        capabilities=Capabilities(input=("text",), reasoning=True),
        upstream_model_id="dep-mini",
    )
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=True),
                _tool_result_followed_by_user_context(system_prompt="Use system."),
                AzureOpenAIResponsesOptions(),
                request,
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_create_kwargs["input"] == [
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
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["max_output_tokens"] == 128


def test_azure_openai_responses_supplied_empty_request_uses_typed_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    request = ResolvedRequest(
        provider="azure-openai",
        endpoint="azure-openai-responses",
        api="azure-openai-responses",
        base_url="https://example.openai.azure.com/openai/v1",
        headers={"Authorization": "Bearer test-key"},
        max_tokens=128,
        capabilities=Capabilities(input=("text",), reasoning=True),
        upstream_model_id="dep-mini",
    )
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                _Model(reasoning=True),
                Context(
                    system_prompt="Use developer instructions.",
                    messages=[UserMessage(role="user", content="hello", timestamp=0.0)],
                ),
                AzureOpenAIResponsesOptions(),
                request,
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_create_kwargs["input"][0] == {
        "role": "developer",
        "content": "Use developer instructions.",
    }
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["max_output_tokens"] == 128


def test_azure_openai_responses_default_catalog_uses_responses_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    clear_default_model_registry()
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "catalog-secret")
    monkeypatch.setenv(
        "AZURE_OPENAI_BASE_URL",
        "https://catalog.azure.example/openai/v1",
    )
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME_MAP", raising=False)
    model = get_default_model_registry().get_model(
        "azure-openai-responses",
        "azure-openai-responses",
        "gpt-5",
    )
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                model,
                _tool_result_followed_by_user_context(
                    system_prompt="Use developer instructions."
                ),
                AzureOpenAIResponsesOptions(),
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_init_kwargs == {
        "api_key": "catalog-secret",
        "azure_endpoint": "https://catalog.azure.example/openai/v1",
        "api_version": "v1",
    }
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["input"] == [
        {"role": "developer", "content": "Use developer instructions."},
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


def test_azure_openai_responses_uses_real_resolved_request_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    monkeypatch.setenv("AZURE_TEST_API_KEY", "catalog-secret")
    monkeypatch.delenv("AZURE_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME_MAP", raising=False)
    model = _bound_azure_model()
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            _stream_raw_parts(
                provider,
                model,
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
                        )
                    ],
                ),
                AzureOpenAIResponsesOptions(),
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_init_kwargs == {
        "api_key": "catalog-secret",
        "azure_endpoint": "https://catalog.azure.example/openai/v1",
        "api_version": "v1",
    }
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["model"] == "vendor/gpt-4o-mini"
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["max_output_tokens"] == 2048
    assert _FakeAsyncAzureOpenAI.last_create_kwargs["input"] == [
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
        }
    ]


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


def _tool_result_followed_by_user_context(*, system_prompt: str) -> Context:
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="azure-openai-responses",
        provider="azure-openai",
        model="gpt-4o-mini",
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


def _fake_openai_module(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAsyncAzureOpenAI.last_init_kwargs = {}
    _FakeAsyncAzureOpenAI.last_create_kwargs = {}
    module = ModuleType("openai")
    module.AsyncAzureOpenAI = _FakeAsyncAzureOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)


def _patch_resolved_request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    upstream_model_id: str | None = None,
    max_tokens: int | None = 1024,
    capabilities: Capabilities | None = None,
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
            api="azure-openai-responses",
            base_url=None,
            headers=headers,
            adapter_compat={},
            max_tokens=resolved_max_tokens,
            capabilities=capabilities or Capabilities(),
            reasoning_effort=None,
            upstream_model_id=upstream_model_id,
        )

    monkeypatch.setattr(
        "loushang.ai.providers.azure_openai_responses.resolve_provider_request",
        _resolve,
    )


def _bound_azure_model() -> Model:
    endpoint = Endpoint(
        id="azure-openai-responses",
        provider="azure-openai",
        api="azure-openai-responses",
        base_url="https://catalog.azure.example/openai/v1",
        auth=Auth(api_key_env="AZURE_TEST_API_KEY"),
        models={
            "gpt-4o-mini-public": Model(
                id="gpt-4o-mini-public",
                provider="azure-openai",
                endpoint="azure-openai-responses",
                capabilities=Capabilities(input=("text", "image"), max_tokens=2048),
                upstream_id="vendor/gpt-4o-mini",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"azure-openai": Provider(id="azure-openai", endpoints={endpoint.id: endpoint})}
    )
    return registry.get_model(
        "azure-openai", "azure-openai-responses", "gpt-4o-mini-public"
    )


class _FakeAsyncAzureOpenAI:
    last_init_kwargs: dict[str, object] = {}
    last_create_kwargs: dict[str, object] = {}

    def __init__(self, **kwargs) -> None:
        type(self).last_init_kwargs = kwargs
        self.responses = _FakeResponses(type(self))


class _FakeResponses:
    def __init__(self, owner: type[_FakeAsyncAzureOpenAI]) -> None:
        self._owner = owner

    async def create(self, **kwargs):
        self._owner.last_create_kwargs = kwargs
        return _FakeStream()


class _FakeStream:
    def __init__(self) -> None:
        self._events = iter(
            [
                SimpleNamespace(
                    type="response.created",
                    response=SimpleNamespace(id="resp_1"),
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
            ]
        )

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@dataclass(frozen=True)
class _Model:
    id: str = "gpt-4o-mini"
    reasoning: bool = False
    input: tuple[str, ...] = ("text", "image")
    max_tokens: int | None = 4096
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, object] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    provider_id: str = "azure-openai-responses"
    endpoint_id: str = "azure-openai-responses"
