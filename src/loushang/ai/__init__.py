from loushang.ai.api import (
    complete,
    complete_structured,
    stream,
)
from loushang.ai.auth import ApiKeyAuth, HeadersAuth, NoAuth, OAuthBearerAuth
from loushang.ai.errors import AIError, AIErrorCode, AIErrorInfo
from loushang.ai.event_stream import AssistantMessageEventStream
from loushang.ai.model import Model
from loushang.ai.model.registry import (
    ModelRegistry,
)
from loushang.ai.model.registry import (
    get_default_model_registry as _get_default_model_registry,
)
from loushang.ai.options import (
    CallOptions,
    ReasoningOptions,
    RetryOptions,
    ThinkingLevel,
    TimeoutOptions,
)
from loushang.ai.structured import (
    StructuredOutputError,
    StructuredOutputOptions,
    StructuredOutputResult,
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
    UsageCost,
    UserMessage,
)
from loushang.ai.usage import (
    usage_from_message,
    usage_payload,
)


def _model_registry() -> ModelRegistry:
    return _get_default_model_registry()


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


__all__ = [
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
    "TimeoutOptions",
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
]
