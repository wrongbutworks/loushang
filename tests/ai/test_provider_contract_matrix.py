from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.provider.protocol import ApiProvider
from loushang.ai.providers.anthropic import AnthropicProvider
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.providers.openai_responses import OpenAIResponsesProvider

REPO_ROOT = Path(__file__).resolve().parents[2]


class CoreAdapterCase(NamedTuple):
    api: str
    module: str
    class_name: str
    provider_type: type[object]


CORE_ADAPTER_MATRIX = (
    CoreAdapterCase(
        "anthropic-messages",
        "loushang.ai.providers.anthropic",
        "AnthropicProvider",
        AnthropicProvider,
    ),
    CoreAdapterCase(
        "openai-completions",
        "loushang.ai.providers.openai_completions",
        "OpenAICompletionsProvider",
        OpenAICompletionsProvider,
    ),
    CoreAdapterCase(
        "openai-responses",
        "loushang.ai.providers.openai_responses",
        "OpenAIResponsesProvider",
        OpenAIResponsesProvider,
    ),
)

PRODUCTION_PROVIDER_FILES = {
    "anthropic.py",
    "openai_completions.py",
    "openai_responses.py",
}
SUPPORT_PROVIDER_FILES = {
    "__init__.py",
    "anthropic_base.py",
    "anthropic_oauth_compat.py",
    "openai_responses_shared.py",
    "provider_helpers.py",
}
TEST_ONLY_PROVIDER_FILES = {"faux.py"}


def test_core_provider_directory_matches_contract_matrix() -> None:
    files = {
        path.name
        for path in (REPO_ROOT / "src/loushang/ai/providers").glob("*.py")
    }

    assert files == (
        PRODUCTION_PROVIDER_FILES | SUPPORT_PROVIDER_FILES | TEST_ONLY_PROVIDER_FILES
    )


def test_core_production_adapters_implement_api_provider_contract() -> None:
    for case in CORE_ADAPTER_MATRIX:
        provider = case.provider_type()

        assert provider.api == case.api
        assert isinstance(provider, ApiProvider)
        assert callable(provider.stream_raw)
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
    assert "`loushang.ai.providers.faux`" in docs
    assert "`loushang.ai.contrib.openai_codex`" in docs
