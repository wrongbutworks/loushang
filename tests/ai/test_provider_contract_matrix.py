from __future__ import annotations

import inspect
from pathlib import Path
from typing import NamedTuple

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.protocols.anthropic_messages import AnthropicMessagesAdapter
from loushang.ai.protocols.openai_chat_completions import OpenAIChatCompletionsAdapter
from loushang.ai.protocols.openai_responses import OpenAIResponsesAdapter
from loushang.ai.provider.protocol import ApiProvider

REPO_ROOT = Path(__file__).resolve().parents[2]


class CoreAdapterCase(NamedTuple):
    api: str
    module: str
    class_name: str
    provider_type: type[object]


CORE_ADAPTER_MATRIX = (
    CoreAdapterCase(
        "anthropic-messages",
        "loushang.ai.protocols.anthropic_messages",
        "AnthropicMessagesAdapter",
        AnthropicMessagesAdapter,
    ),
    CoreAdapterCase(
        "openai-completions",
        "loushang.ai.protocols.openai_chat_completions",
        "OpenAIChatCompletionsAdapter",
        OpenAIChatCompletionsAdapter,
    ),
    CoreAdapterCase(
        "openai-responses",
        "loushang.ai.protocols.openai_responses",
        "OpenAIResponsesAdapter",
        OpenAIResponsesAdapter,
    ),
)


def test_core_production_adapters_implement_api_provider_contract() -> None:
    for case in CORE_ADAPTER_MATRIX:
        provider = case.provider_type()

        assert provider.api == case.api
        assert isinstance(provider, ApiProvider)
        assert callable(provider.invoke_raw)
        assert list(inspect.signature(provider.invoke_raw).parameters) == ["request"]
        assert not hasattr(provider, "stream_simple")


def test_builtin_registration_is_frozen_to_core_adapter_matrix() -> None:
    registry = ApiProviderRegistry()

    register_builtin_ai_providers(registry)

    assert sorted(provider.api for provider in registry.list_api_providers()) == [
        case.api for case in CORE_ADAPTER_MATRIX
    ]


def test_contract_matrix_document_matches_core_adapters() -> None:
    docs = (
        REPO_ROOT
        / "docs/internals/architecture/ai/core-provider-adapter-contract-matrix.md"
    ).read_text(encoding="utf-8")

    for case in CORE_ADAPTER_MATRIX:
        assert f"`{case.api}`" in docs
        assert f"`{case.module}`" in docs
        assert f"`{case.class_name}`" in docs
    assert "`loushang.ai.protocols.faux`" in docs
