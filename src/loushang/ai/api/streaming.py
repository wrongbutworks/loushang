from __future__ import annotations

from dataclasses import replace

from loushang.ai.api_registry import get_default_api_provider_registry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.context import NormalizedContext, normalize_context_result
from loushang.ai.diagnostics import NormalizationDiagnostic
from loushang.ai.errors import UnsupportedCapabilityError
from loushang.ai.model import (
    AnthropicMessagesConfig,
    Model,
    OpenAICompletionsConfig,
    OpenAIResponsesConfig,
)
from loushang.ai.options import (
    CallOptions,
    PairingMode,
    is_reasoning_requested,
)
from loushang.ai.provider import (
    ProviderInvocationMode,
    normalize_provider_request_for_api,
    resolve_request_for_model,
)
from loushang.ai.provider.invocation import (
    call_api_provider_stream,
    validate_provider_request,
)
from loushang.ai.structured import (
    StructuredOutputOptions,
    StructuredOutputResult,
    get_structured_output_options,
    parse_structured_output,
    with_structured_output_options,
)
from loushang.ai.types import ImagePart, ToolResultMessage, UserMessage


def _has_image_input(normalized_context: NormalizedContext) -> bool:
    for message in normalized_context.messages:
        if (
            isinstance(message, UserMessage)
            and isinstance(message.content, list)
            and any(isinstance(part, ImagePart) for part in message.content)
        ):
            return True
        if isinstance(message, ToolResultMessage) and any(
            isinstance(part, ImagePart) for part in message.content
        ):
            return True
    return False


def _has_tools(normalized_context: NormalizedContext) -> bool:
    return bool(normalized_context.tools)


def _requests_reasoning(options) -> bool:
    return is_reasoning_requested(options)


def _requests_structured_output(options) -> bool:
    return get_structured_output_options(options) is not None


def _requests_temperature(options) -> bool:
    return options is not None and getattr(options, "temperature", None) is not None


def _requests_tool_choice(options) -> bool:
    if options is None:
        return False
    tool_choice = getattr(options, "tool_choice", None)
    return tool_choice is not None and tool_choice != "none"


def _supports(capabilities, field: str) -> bool:
    return bool(getattr(capabilities, field, False))


def _adapter_supports_long_cache_retention(adapter_config: object) -> bool:
    if isinstance(
        adapter_config,
        OpenAICompletionsConfig | OpenAIResponsesConfig | AnthropicMessagesConfig,
    ):
        return adapter_config.long_cache_retention
    return True


def _adapter_consumes_cache_key(adapter_config: object) -> bool:
    if isinstance(adapter_config, OpenAICompletionsConfig):
        return (
            adapter_config.prompt_cache_key or adapter_config.session_affinity_headers
        )
    if isinstance(adapter_config, OpenAIResponsesConfig):
        return (
            adapter_config.prompt_cache_key
            or adapter_config.session_id_header
            or adapter_config.session_affinity_headers
        )
    if isinstance(adapter_config, AnthropicMessagesConfig):
        return adapter_config.session_affinity_headers
    return True


def _normalize_cache_key_for_adapter(
    options: CallOptions | None,
    adapter_config: object,
) -> CallOptions | None:
    """Return call options safe for the resolved adapter."""
    if options is None:
        return None

    cache_key = getattr(options, "cache_key", None)
    if not isinstance(cache_key, str) or not cache_key:
        return options

    if getattr(options, "cache_retention", None) == "none":
        return replace(options, cache_key=None)

    if _adapter_consumes_cache_key(adapter_config):
        return options

    return replace(options, cache_key=None)


def _validate_explicit_adapter_config(model, resolved, options) -> None:
    if options is None:
        return
    adapter_config = getattr(resolved, "adapter_config", None)
    cache_retention = getattr(options, "cache_retention", None)
    if cache_retention == "long" and not _adapter_supports_long_cache_retention(
        adapter_config
    ):
        raise UnsupportedCapabilityError(
            f"Model {model.id!r} does not support long cache retention",
            provider=getattr(resolved, "provider", None),
            endpoint=getattr(resolved, "endpoint", None),
            model=getattr(model, "id", None),
            details={"capability": "cache_long_retention"},
        )


def _validate_capability(
    model,
    capabilities,
    normalized_context: NormalizedContext,
    options,
    *,
    require_stream: bool,
) -> None:
    if require_stream and not _supports(capabilities, "stream"):
        raise UnsupportedCapabilityError(
            f"Model {model.id!r} does not support streaming",
            model=getattr(model, "id", None),
            details={"capability": "stream"},
        )

    if (
        _has_tools(normalized_context) or _requests_tool_choice(options)
    ) and not _supports(capabilities, "tool_use"):
        raise UnsupportedCapabilityError(
            f"Model {model.id!r} does not support tool use",
            model=getattr(model, "id", None),
            details={"capability": "tool_use"},
        )

    if _requests_reasoning(options) and not _supports(
        capabilities, "reasoning"
    ):
        raise UnsupportedCapabilityError(
            f"Model {model.id!r} does not support reasoning",
            model=getattr(model, "id", None),
            details={"capability": "reasoning"},
        )

    if _requests_structured_output(options) and not _supports(
        capabilities, "structured_output"
    ):
        raise UnsupportedCapabilityError(
            f"Model {model.id!r} does not support structured output",
            model=getattr(model, "id", None),
            details={"capability": "structured_output"},
        )

    if _requests_temperature(options) and not _supports(capabilities, "temperature"):
        raise UnsupportedCapabilityError(
            f"Model {model.id!r} does not support temperature",
            model=getattr(model, "id", None),
            details={"capability": "temperature"},
        )

    supports_image_input = bool(getattr(capabilities, "supports_image_input", False))
    if _has_image_input(normalized_context) and not supports_image_input:
        raise UnsupportedCapabilityError(
            f"Model {model.id!r} does not support image input",
            model=getattr(model, "id", None),
            details={"capability": "image_input"},
        )

def _resolve_api_provider_registry(api_provider_registry=None):
    if api_provider_registry is not None:
        return api_provider_registry
    default_registry = get_default_api_provider_registry()
    if not default_registry.list_api_providers():
        register_builtin_ai_providers(default_registry)
    return default_registry


def _validate_call_options(options: object | None) -> CallOptions | None:
    if options is None or isinstance(options, CallOptions):
        return options
    raise TypeError("options must be CallOptions")


def _supports_structured_output_mapping(provider: object) -> bool:
    return bool(getattr(provider, "supports_structured_output", False))


def _resolve_pairing_mode(options) -> PairingMode:
    if options is None:
        return "strict"
    pairing_mode = getattr(options, "pairing_mode", "strict")
    if pairing_mode == "repair":
        return "repair"
    return "strict"


def _emit_normalization_diagnostics(
    options: CallOptions | None,
    diagnostics: tuple[NormalizationDiagnostic, ...],
) -> None:
    if not diagnostics:
        return
    from loushang.ai.trace import emit_trace
    from loushang.observability import get_log

    log = get_log(__name__).bind(component="AINormalization")
    for diagnostic in diagnostics:
        payload = {
            "type": "normalization:diagnostic",
            "code": diagnostic.code,
            "path": diagnostic.path,
            "message": diagnostic.message,
            "level": diagnostic.level,
        }
        emit_trace(options, payload)
        if diagnostic.level == "warning":
            log.warning(
                diagnostic.message,
                code=diagnostic.code,
                path=diagnostic.path,
                level=diagnostic.level,
            )
        else:
            log.debug(
                diagnostic.message,
                code=diagnostic.code,
                path=diagnostic.path,
                level=diagnostic.level,
        )


async def _start_stream(
    model: Model,
    context,
    options: CallOptions | None = None,
    *,
    provider_registry=None,
    mode: ProviderInvocationMode,
    require_stream: bool,
):
    options = _validate_call_options(options)
    resolved = resolve_request_for_model(model, options=options)
    resolved_model = resolved.model
    options = _normalize_cache_key_for_adapter(
        options,
        getattr(resolved, "adapter_config", None),
    )
    normalization_result = normalize_context_result(
        context,
        model=resolved_model,
        pairing_mode=_resolve_pairing_mode(options),
    )
    normalized = normalization_result.context
    _emit_normalization_diagnostics(options, normalization_result.diagnostics)
    resolved = replace(
        resolved,
        context=normalized,
        options=options,
        mode=mode,
    )
    _validate_capability(
        resolved_model,
        resolved.capabilities,
        normalized,
        options,
        require_stream=require_stream,
    )
    _validate_explicit_adapter_config(resolved_model, resolved, options)
    provider = _resolve_api_provider_registry(provider_registry).get_api_provider(
        resolved.api
    )
    resolved = normalize_provider_request_for_api(provider.api, resolved)
    validate_provider_request(provider, resolved)
    if get_structured_output_options(
        options
    ) is not None and not _supports_structured_output_mapping(provider):
        raise UnsupportedCapabilityError(
            f"Provider API {resolved.api!r} does not support structured output mapping",
            provider=getattr(resolved, "provider", None),
            endpoint=getattr(resolved, "endpoint", None),
            model=resolved_model.id,
            details={
                "capability": "structured_output_mapping",
                "api": resolved.api,
            },
        )
    return await call_api_provider_stream(provider, resolved)


async def stream(
    model: Model,
    context,
    options: CallOptions | None = None,
    *,
    provider_registry=None,
):
    return await _start_stream(
        model,
        context,
        options,
        provider_registry=provider_registry,
        mode="stream",
        require_stream=True,
    )


async def complete(
    model: Model,
    context,
    options: CallOptions | None = None,
    *,
    provider_registry=None,
):
    event_stream = await _start_stream(
        model,
        context,
        options,
        provider_registry=provider_registry,
        mode="complete",
        require_stream=False,
    )
    return await event_stream.result()


async def complete_structured(
    model: Model,
    context,
    output: StructuredOutputOptions | None = None,
    *,
    options: CallOptions | None = None,
    provider_registry=None,
) -> StructuredOutputResult:
    structured_output = output or get_structured_output_options(options)
    if structured_output is None:
        raise ValueError("complete_structured requires StructuredOutputOptions")
    call_options = with_structured_output_options(options, structured_output)
    message = await complete(
        model,
        context,
        call_options,
        provider_registry=provider_registry,
    )
    return parse_structured_output(message, structured_output)
