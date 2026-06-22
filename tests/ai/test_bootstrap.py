from __future__ import annotations

import importlib.util

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.auth.registry import OAuthProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.contrib.openai_codex import register_openai_codex_contrib
from loushang.ai.model import Endpoint, Model
from loushang.ai.model.registry import (
    ModelRegistry,
    clear_default_model_registry,
    get_default_model_registry,
)


def test_register_builtin_ai_providers_excludes_removed_adapters() -> None:
    clear_default_model_registry()
    model_registry = get_default_model_registry()
    model_registry.register_endpoint(
        "amazon-bedrock",
        Endpoint(
            id="bedrock-converse-stream",
            provider="amazon-bedrock",
            api="bedrock-converse-stream",
            models={
                "claude": Model(
                    id="claude",
                    provider="amazon-bedrock",
                    endpoint="bedrock-converse-stream",
                )
            },
        ),
    )
    registry = ApiProviderRegistry()

    register_builtin_ai_providers(registry)

    apis = {provider.api for provider in registry.list_api_providers()}
    assert "azure-openai-responses" not in apis
    assert "bedrock-converse-stream" not in apis
    assert "openai-codex-responses" not in apis


def test_azure_openai_provider_module_is_not_in_core() -> None:
    assert importlib.util.find_spec(
        "loushang.ai.providers.azure_openai_responses"
    ) is None


def test_bedrock_provider_module_is_not_in_core() -> None:
    assert importlib.util.find_spec("loushang.ai.providers.bedrock_converse") is None


def test_openai_codex_contrib_registers_api_and_catalog_explicitly() -> None:
    api_registry = ApiProviderRegistry()
    model_registry = ModelRegistry()
    oauth_registry = OAuthProviderRegistry()

    register_openai_codex_contrib(
        api_registry=api_registry,
        oauth_registry=oauth_registry,
        model_registry=model_registry,
    )

    apis = {provider.api for provider in api_registry.list_api_providers()}
    assert "openai-codex-responses" in apis
    assert model_registry.get_provider("openai-codex") is not None
    assert (
        model_registry.get_model(
            "openai-codex",
            "openai-codex-responses",
            "gpt-5.3-codex",
        ).id
        == "gpt-5.3-codex"
    )
