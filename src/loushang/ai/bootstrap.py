from __future__ import annotations

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.protocols.anthropic_messages import AnthropicMessagesAdapter
from loushang.ai.protocols.openai_chat_completions import OpenAIChatCompletionsAdapter
from loushang.ai.protocols.openai_responses import OpenAIResponsesAdapter


def register_builtin_ai_providers(
    registry: ApiProviderRegistry,
) -> None:
    registry.register_api_provider(AnthropicMessagesAdapter())
    registry.register_api_provider(OpenAIChatCompletionsAdapter())
    registry.register_api_provider(OpenAIResponsesAdapter())
