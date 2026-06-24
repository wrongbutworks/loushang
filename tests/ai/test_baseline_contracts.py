from __future__ import annotations

import loushang.ai as ai
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers

ROOT_STABLE_EXPORTS = {
    "AssistantMessage",
    "AssistantMessageEvent",
    "AssistantMessageEventStream",
    "Context",
    "Message",
    "Model",
    "AIError",
    "AIErrorCode",
    "AIErrorInfo",
    "CallOptions",
    "ReasoningOptions",
    "RetryOptions",
    "TimeoutOptions",
    "StructuredOutputOptions",
    "Tool",
    "ToolCall",
    "Usage",
    "complete",
    "complete_structured",
    "get_model",
    "list_models",
    "stream",
}

ADVANCED_ROOT_EXPORTS_REMOVED = {
    "ApiProviderRegistry",
    "AnthropicOptions",
    "OpenAICodexResponsesOptions",
    "OpenAICompletionsOptions",
    "OpenAIResponsesOptions",
    "clear_api_providers",
    "get_api_provider",
    "get_env_api_key",
    "get_providers",
    "list_api_providers",
    "register_api_provider",
    "reset_api_providers",
}

REGISTERED_CORE_PROVIDER_APIS = (
    "anthropic-messages",
    "openai-completions",
    "openai-responses",
)


def test_root_exports_include_stable_core_entrypoints() -> None:
    assert ROOT_STABLE_EXPORTS <= set(ai.__all__)


def test_advanced_exports_are_not_root_stable_exports() -> None:
    for export in ADVANCED_ROOT_EXPORTS_REMOVED:
        assert export not in ai.__all__
        assert not hasattr(ai, export)


def test_builtin_provider_registration_stays_on_core_protocol_adapters() -> None:
    registry = ApiProviderRegistry()

    register_builtin_ai_providers(registry)

    assert tuple(sorted(provider.api for provider in registry.list_api_providers())) == (
        REGISTERED_CORE_PROVIDER_APIS
    )
