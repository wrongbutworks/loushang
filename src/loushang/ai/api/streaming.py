from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from loushang.ai.api_registry import get_default_api_provider_registry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.context import normalize_context
from loushang.ai.options import PairingMode
from loushang.ai.provider import resolve_request_for_model
from loushang.ai.provider.invocation import (
    call_api_provider_stream,
    call_api_provider_stream_simple,
)
from loushang.ai.types import ImagePart, ToolResultMessage, UserMessage


def _has_image_input(normalized_context: Mapping[str, Any]) -> bool:
    for message in normalized_context.get("messages", []):
        if isinstance(message, UserMessage) and isinstance(message.content, list):
            if any(isinstance(part, ImagePart) for part in message.content):
                return True
        if isinstance(message, ToolResultMessage):
            if any(isinstance(part, ImagePart) for part in message.content):
                return True
    return False


def _has_tools(normalized_context: Mapping[str, Any]) -> bool:
    return bool(normalized_context.get("tools"))


def _requests_reasoning(normalized_context: Mapping[str, Any], options) -> bool:
    if normalized_context.get("emit_thinking"):
        return True
    if options is None:
        return False
    if getattr(options, "reasoning", None):
        return True
    if getattr(options, "reasoning_summary", None):
        return True
    if getattr(options, "thinking_enabled", False):
        return True
    if getattr(options, "thinking_budget_tokens", None):
        return True
    if getattr(options, "effort", None):
        return True
    return False


def _requests_structured_output(
    normalized_context: Mapping[str, Any], options
) -> bool:
    fields = (
        "response_format",
        "responseFormat",
        "structured_output",
        "structuredOutput",
        "json_schema",
        "jsonSchema",
        "output_schema",
        "outputSchema",
        "response_model",
        "responseModel",
    )
    return _has_any_context_or_option_value(normalized_context, options, fields)


def _requests_attachment(normalized_context: Mapping[str, Any], options) -> bool:
    fields = ("attachment", "attachments", "file_ids", "fileIds", "files")
    return _has_any_context_or_option_value(normalized_context, options, fields)


def _has_any_context_or_option_value(
    normalized_context: Mapping[str, Any],
    options,
    fields: tuple[str, ...],
) -> bool:
    if any(normalized_context.get(field) for field in fields):
        return True
    if options is None:
        return False
    return any(getattr(options, field, None) for field in fields)


def _requests_temperature(options) -> bool:
    return options is not None and getattr(options, "temperature", None) is not None


def _requests_tool_choice(options) -> bool:
    if options is None:
        return False
    tool_choice = getattr(options, "tool_choice", None)
    return tool_choice is not None and tool_choice != "none"


def _supports(capabilities, field: str) -> bool:
    return bool(getattr(capabilities, field, False))


def _validate_capability(
    model,
    capabilities,
    normalized_context: Mapping[str, Any],
    options,
    *,
    require_stream: bool,
) -> None:
    if require_stream and not _supports(capabilities, "stream"):
        raise ValueError(f"Model {model.id!r} does not support streaming")

    if (_has_tools(normalized_context) or _requests_tool_choice(options)) and not _supports(
        capabilities, "tool_use"
    ):
        raise ValueError(f"Model {model.id!r} does not support tool use")

    if _requests_reasoning(normalized_context, options) and not _supports(
        capabilities, "reasoning"
    ):
        raise ValueError(f"Model {model.id!r} does not support reasoning")

    if _requests_structured_output(normalized_context, options) and not _supports(
        capabilities, "structured_output"
    ):
        raise ValueError(f"Model {model.id!r} does not support structured output")

    if _requests_temperature(options) and not _supports(capabilities, "temperature"):
        raise ValueError(f"Model {model.id!r} does not support temperature")

    supports_image_input = bool(getattr(capabilities, "supports_image_input", False))
    if _has_image_input(normalized_context) and not supports_image_input:
        raise ValueError(f"Model {model.id!r} does not support image input")

    if _requests_attachment(normalized_context, options) and not _supports(
        capabilities, "attachment"
    ):
        raise ValueError(f"Model {model.id!r} does not support attachment")


def _resolve_api_provider_registry(api_provider_registry=None):
    if api_provider_registry is not None:
        return api_provider_registry
    default_registry = get_default_api_provider_registry()
    if not default_registry.list_api_providers():
        register_builtin_ai_providers(default_registry)
    return default_registry


def _resolve_pairing_mode(options) -> PairingMode:
    if options is None:
        return "strict"
    pairing_mode = getattr(options, "pairing_mode", "strict")
    if pairing_mode == "repair":
        return "repair"
    return "strict"


def _normalization_model(model, resolved):
    return SimpleNamespace(
        api=resolved.api,
        provider_id=resolved.provider,
        endpoint_id=getattr(resolved, "endpoint", getattr(model, "endpoint_id", None)),
        id=model.id,
    )


async def _start_stream(
    model,
    context,
    options=None,
    *,
    registry=None,
    require_stream: bool,
    simple: bool,
):
    resolved = resolve_request_for_model(model, options=options)
    normalized = normalize_context(
        context,
        model=_normalization_model(model, resolved),
        pairing_mode=_resolve_pairing_mode(options),
    )
    _validate_capability(
        model,
        resolved.capabilities,
        normalized,
        options,
        require_stream=require_stream,
    )
    provider = _resolve_api_provider_registry(registry).get_api_provider(resolved.api)
    if simple:
        return await call_api_provider_stream_simple(
            provider,
            model,
            normalized,
            options,
            resolved,
        )
    return await call_api_provider_stream(
        provider, model, normalized, options, resolved
    )


async def stream(model, context, options=None, *, registry=None):
    return await _start_stream(
        model,
        context,
        options,
        registry=registry,
        require_stream=True,
        simple=False,
    )


async def complete(model, context, options=None, *, registry=None):
    event_stream = await _start_stream(
        model,
        context,
        options,
        registry=registry,
        require_stream=False,
        simple=False,
    )
    return await event_stream.result()


async def stream_simple(model, context, options=None, *, registry=None):
    return await _start_stream(
        model,
        context,
        options,
        registry=registry,
        require_stream=True,
        simple=True,
    )


async def complete_simple(model, context, options=None, *, registry=None):
    event_stream = await _start_stream(
        model,
        context,
        options,
        registry=registry,
        require_stream=False,
        simple=True,
    )
    return await event_stream.result()
