from loushang.ai.api import complete, complete_simple, stream, stream_simple
from loushang.ai.api_registry import (
    ApiProviderRegistry,
    get_default_api_provider_registry,
)
from loushang.ai.auth import get_env_api_key
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.context import normalize_context
from loushang.ai.event_stream import (
    AssistantMessageEventStream,
    EventStream,
    create_assistant_message_event_stream,
)
from loushang.ai.model import Model
from loushang.ai.model.registry import (
    get_default_model_registry as _get_default_model_registry,
)
from loushang.ai.options import (
    AnthropicOptions,
    CacheRetention,
    OpenAICodexResponsesOptions,
    OpenAICompletionsOptions,
    OpenAIResponsesOptions,
    PairingMode,
    SimpleStreamOptions,
    StreamOptions,
    ThinkingBudgets,
    ThinkingLevel,
    Transport,
)
from loushang.ai.pricing import calculate_cost, models_are_equal
from loushang.ai.tool import (
    normalize_tool_call_id_for_model,
    transform_messages,
    validate_tool_arguments,
    validate_tool_call,
)
from loushang.ai.types import (
    AssistantMessage,
    AssistantMessageEvent,
    Context,
    ImagePart,
    Message,
    StopReason,
    TextPart,
    ThinkingPart,
    Tool,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from loushang.ai.utils import (
    get_overflow_patterns,
    is_context_overflow,
    parse_streaming_json,
)


def _model_registry():
    return _get_default_model_registry()


def _api_provider_registry():
    return get_default_api_provider_registry()


def get_model(provider: str, endpoint: str, model_id: str) -> Model:
    return _model_registry().get_model(provider, endpoint, model_id)


def list_models(
    *,
    provider: str | None = None,
    endpoint: str | None = None,
    model_id: str | None = None,
) -> list[Model]:
    return _model_registry().list_models(
        provider=provider,
        endpoint=endpoint,
        model_id=model_id,
    )


def get_providers() -> list[str]:
    return _model_registry().get_providers()


def register_api_provider(provider) -> None:
    _api_provider_registry().register_api_provider(provider)


def get_api_provider(api: str):
    return _api_provider_registry().get_api_provider(api)


def list_api_providers():
    return _api_provider_registry().list_api_providers()


def clear_api_providers() -> None:
    _api_provider_registry().clear_api_providers()


def reset_api_providers(
    *,
    anthropic_base_url: str | None = None,
    openai_base_url: str | None = None,
) -> None:
    clear_api_providers()
    register_builtin_ai_providers(
        _api_provider_registry(),
        anthropic_base_url=anthropic_base_url,
        openai_base_url=openai_base_url,
    )


__all__ = [
    "ApiProviderRegistry",
    "AssistantMessage",
    "AssistantMessageEvent",
    "AssistantMessageEventStream",
    "EventStream",
    "Context",
    "Message",
    "Model",
    "StopReason",
    "StreamOptions",
    "SimpleStreamOptions",
    "AnthropicOptions",
    "OpenAICompletionsOptions",
    "OpenAICodexResponsesOptions",
    "OpenAIResponsesOptions",
    "PairingMode",
    "ThinkingLevel",
    "ThinkingBudgets",
    "CacheRetention",
    "Transport",
    "ImagePart",
    "TextPart",
    "ThinkingPart",
    "Tool",
    "ToolCall",
    "ToolResultMessage",
    "UserMessage",
    "Usage",
    "calculate_cost",
    "clear_api_providers",
    "complete",
    "complete_simple",
    "create_assistant_message_event_stream",
    "get_api_provider",
    "get_env_api_key",
    "get_model",
    "get_overflow_patterns",
    "get_providers",
    "is_context_overflow",
    "list_api_providers",
    "list_models",
    "models_are_equal",
    "normalize_context",
    "normalize_tool_call_id_for_model",
    "parse_streaming_json",
    "register_api_provider",
    "register_builtin_ai_providers",
    "reset_api_providers",
    "stream",
    "stream_simple",
    "transform_messages",
    "validate_tool_arguments",
    "validate_tool_call",
]
