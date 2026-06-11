from __future__ import annotations

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.model.registry import get_default_model_registry
from loushang.ai.providers.anthropic import AnthropicProvider
from loushang.ai.providers.azure_openai_responses import AzureOpenAIResponsesProvider
from loushang.ai.providers.bedrock_converse import BedrockConverseProvider
from loushang.ai.providers.openai_codex_responses import OpenAICodexResponsesProvider
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.providers.openai_responses import OpenAIResponsesProvider


def register_builtin_ai_providers(
    registry: ApiProviderRegistry,
    *,
    anthropic_base_url: str | None = None,
    openai_base_url: str | None = None,
) -> None:
    model_registry = get_default_model_registry()
    endpoints = model_registry.list_endpoints()
    has_anthropic_endpoint = any(
        endpoint.api == "anthropic-messages" for endpoint in endpoints
    )
    has_openai_compatible_endpoint = any(
        endpoint.api in {"openai-completions", "openai-responses"}
        for endpoint in endpoints
    )
    has_openai_codex_endpoint = any(
        endpoint.api == "openai-codex-responses" for endpoint in endpoints
    )
    has_azure_openai_responses_endpoint = any(
        endpoint.api == "azure-openai-responses" for endpoint in endpoints
    )
    has_bedrock_endpoint = any(
        endpoint.api == "bedrock-converse-stream" for endpoint in endpoints
    )

    if anthropic_base_url is not None or has_anthropic_endpoint:
        registry.register_api_provider(AnthropicProvider())
    if openai_base_url is not None or has_openai_compatible_endpoint:
        registry.register_api_provider(
            OpenAICompletionsProvider(base_url=openai_base_url)
        )
        registry.register_api_provider(
            OpenAIResponsesProvider(base_url=openai_base_url)
        )
    if has_openai_codex_endpoint:
        registry.register_api_provider(OpenAICodexResponsesProvider())
    if has_azure_openai_responses_endpoint:
        registry.register_api_provider(AzureOpenAIResponsesProvider())
    if has_bedrock_endpoint:
        registry.register_api_provider(BedrockConverseProvider())
