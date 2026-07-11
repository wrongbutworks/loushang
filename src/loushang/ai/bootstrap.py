from __future__ import annotations

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.providers.anthropic import AnthropicProvider
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.providers.openai_responses import OpenAIResponsesProvider


def register_builtin_ai_providers(
    registry: ApiProviderRegistry,
) -> None:
    registry.register_api_provider(AnthropicProvider())
    registry.register_api_provider(OpenAICompletionsProvider())
    registry.register_api_provider(OpenAIResponsesProvider())
