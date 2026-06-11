from __future__ import annotations

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.model import Endpoint, Model
from loushang.ai.model.registry import (
    clear_default_model_registry,
    get_default_model_registry,
)


def test_register_builtin_ai_providers_includes_azure_and_bedrock() -> None:
    clear_default_model_registry()
    model_registry = get_default_model_registry()
    model_registry.register_endpoint(
        "azure-openai-responses",
        Endpoint(
            id="azure-openai-responses",
            provider="azure-openai-responses",
            api="azure-openai-responses",
            models={
                "gpt-4o-mini": Model(
                    id="gpt-4o-mini",
                    provider="azure-openai-responses",
                    endpoint="azure-openai-responses",
                )
            },
        ),
    )
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
    assert "azure-openai-responses" in apis
    assert "bedrock-converse-stream" in apis
