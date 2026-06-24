from __future__ import annotations

import inspect
from typing import NamedTuple

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.provider.protocol import ApiProvider
from loushang.ai.providers.anthropic import AnthropicProvider
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.providers.openai_responses import OpenAIResponsesProvider


class CoreAdapterCase(NamedTuple):
    api: str
    provider_type: type[object]


CORE_ADAPTERS = (
    CoreAdapterCase("anthropic-messages", AnthropicProvider),
    CoreAdapterCase("openai-completions", OpenAICompletionsProvider),
    CoreAdapterCase("openai-responses", OpenAIResponsesProvider),
)


def test_core_adapters_implement_stream_raw_contract() -> None:
    for case in CORE_ADAPTERS:
        provider = case.provider_type()

        assert isinstance(provider, ApiProvider)
        assert provider.api == case.api
        assert callable(provider.stream_raw)
        assert list(inspect.signature(provider.stream_raw).parameters) == ["request"]
        assert not hasattr(provider, "stream_simple")


def test_builtin_registration_matches_core_contracts() -> None:
    registry = ApiProviderRegistry()

    register_builtin_ai_providers(registry)

    assert sorted(provider.api for provider in registry.list_api_providers()) == [
        case.api for case in CORE_ADAPTERS
    ]
