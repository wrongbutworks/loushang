from __future__ import annotations

import loushang.ai as ai
import loushang.ai.api as ai_api
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers

ROOT_STABLE_EXPORTS = (
    "AssistantMessage",
    "AssistantMessageEvent",
    "AssistantMessageEventStream",
    "Context",
    "Message",
    "Model",
    "StopReason",
    "AIError",
    "AIErrorCode",
    "AIErrorInfo",
    "ApiKeyAuth",
    "CallOptions",
    "HeadersAuth",
    "NoAuth",
    "OAuthBearerAuth",
    "ReasoningOptions",
    "RetryOptions",
    "ThinkingLevel",
    "StructuredOutputError",
    "StructuredOutputOptions",
    "StructuredOutputResult",
    "ImagePart",
    "TextPart",
    "ThinkingPart",
    "Tool",
    "ToolCall",
    "ToolResultMessage",
    "UserMessage",
    "Usage",
    "UsageCost",
    "complete",
    "complete_structured",
    "get_model",
    "list_models",
    "stream",
    "usage_from_message",
    "usage_payload",
)

API_INVOCATION_EXPORTS = (
    "complete",
    "complete_structured",
    "stream",
)

API_NON_ENTRYPOINTS = (
    "AgentRuntimeHints",
    "AIError",
    "AIErrorCode",
    "AIErrorInfo",
    "CacheRetention",
    "CallOptions",
    "CompressionPolicy",
    "ReasoningOptions",
    "RetryOptions",
    "SessionBudget",
    "StopReason",
    "TextSignatureV1",
    "ThinkingLevel",
)

ADVANCED_ROOT_EXPORTS_REMOVED = {
    "ApiProviderRegistry",
    "AnthropicOptions",
    "ModelRegistry",
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


def test_root_exports_match_stable_facade_snapshot() -> None:
    assert tuple(ai.__all__) == ROOT_STABLE_EXPORTS


def test_api_package_exports_only_invocation_entrypoints() -> None:
    assert tuple(ai_api.__all__) == API_INVOCATION_EXPORTS
    for name in API_INVOCATION_EXPORTS:
        assert getattr(ai_api, name) is getattr(ai, name)
    for name in API_NON_ENTRYPOINTS:
        assert not hasattr(ai_api, name)


def test_advanced_exports_are_not_root_stable_exports() -> None:
    for export in ADVANCED_ROOT_EXPORTS_REMOVED:
        assert export not in ai.__all__
        assert not hasattr(ai, export)


def test_builtin_provider_registration_stays_on_core_protocol_adapters() -> None:
    registry = ApiProviderRegistry()

    register_builtin_ai_providers(registry)

    assert tuple(
        sorted(provider.api for provider in registry.list_api_providers())
    ) == (REGISTERED_CORE_PROVIDER_APIS)
