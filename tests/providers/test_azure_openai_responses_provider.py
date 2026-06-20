from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest

from loushang.ai.options import AzureOpenAIResponsesOptions
from loushang.ai.providers.azure_openai_responses import AzureOpenAIResponsesProvider
from loushang.ai.types import UserMessage


def test_azure_openai_responses_uses_azure_client_and_deployment_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_openai_module(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME_MAP", "gpt-4o-mini=dep-mini")
    _patch_resolved_request(monkeypatch)
    provider = AzureOpenAIResponsesProvider()

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(id="gpt-4o-mini"),
                {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
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
            provider._stream_raw_parts(
                _Model(id="gpt-4o-mini_public"),
                {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
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
            provider._stream_raw_parts(
                _Model(id="gpt-4o-mini_public"),
                {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
                AzureOpenAIResponsesOptions(
                    api_key="test-key",
                    azure_base_url="https://example.openai.azure.com/openai/v1",
                ),
            )
        )
    )

    assert _FakeAsyncAzureOpenAI.last_create_kwargs["model"] == "vendor/gpt-4o-mini"


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


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
) -> None:
    def _resolve(_model, options=None):
        headers = {}
        api_key = getattr(options, "api_key", None) if options is not None else None
        if isinstance(api_key, str) and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return SimpleNamespace(
            api="azure-openai-responses",
            headers=headers,
            base_url=None,
            compat={},
            max_tokens=1024,
            reasoning_effort=None,
            upstream_model_id=upstream_model_id,
        )

    monkeypatch.setattr(
        "loushang.ai.providers.azure_openai_responses.resolve_request_for_model",
        _resolve,
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
