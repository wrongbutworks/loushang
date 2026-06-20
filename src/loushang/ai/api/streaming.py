from __future__ import annotations

from types import SimpleNamespace

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


def _has_image_input(normalized_context: dict) -> bool:
    for message in normalized_context.get("messages", []):
        if isinstance(message, UserMessage) and isinstance(message.content, list):
            if any(isinstance(part, ImagePart) for part in message.content):
                return True
        if isinstance(message, ToolResultMessage):
            if any(isinstance(part, ImagePart) for part in message.content):
                return True
    return False


def _requests_thinking(normalized_context: dict, options) -> bool:
    if normalized_context.get("emit_thinking"):
        return True
    if options is None:
        return False
    if getattr(options, "reasoning", None):
        return True
    if getattr(options, "thinking_enabled", False):
        return True
    if getattr(options, "thinking_budget_tokens", None):
        return True
    if getattr(options, "effort", None):
        return True
    return False


def _validate_capability(
    model, capabilities, normalized_context: dict, options
) -> None:
    supports_image_input = bool(getattr(capabilities, "supports_image_input", False))
    if _has_image_input(normalized_context) and not supports_image_input:
        raise ValueError(f"Model {model.id!r} does not support image input")

    supports_thinking = bool(getattr(capabilities, "supports_thinking", False))
    if _requests_thinking(normalized_context, options) and not supports_thinking:
        raise ValueError(f"Model {model.id!r} does not support thinking")


def _resolve_api_provider_registry(api_provider_registry=None):
    if api_provider_registry is not None:
        return api_provider_registry
    default_registry = get_default_api_provider_registry()
    if not default_registry.list_api_providers():
        register_builtin_ai_providers(default_registry)
    return default_registry


def _resolve_pairing_mode(options) -> PairingMode:
    if options is None:
        return "repair"
    pairing_mode = getattr(options, "pairing_mode", "repair")
    if pairing_mode == "strict":
        return "strict"
    return "repair"


def _normalization_model(model, resolved):
    return SimpleNamespace(
        api=resolved.api,
        provider_id=resolved.provider,
        id=model.id,
    )


async def stream(model, context, options=None, *, registry=None):
    resolved = resolve_request_for_model(model, options=options)
    normalized = normalize_context(
        context,
        model=_normalization_model(model, resolved),
        pairing_mode=_resolve_pairing_mode(options),
    )
    _validate_capability(model, resolved.capabilities, normalized, options)
    provider = _resolve_api_provider_registry(registry).get_api_provider(resolved.api)
    return await call_api_provider_stream(
        provider, model, normalized, options, resolved
    )


async def complete(model, context, options=None, *, registry=None):
    event_stream = await stream(model, context, options, registry=registry)
    return await event_stream.result()


async def stream_simple(model, context, options=None, *, registry=None):
    resolved = resolve_request_for_model(model, options=options)
    normalized = normalize_context(
        context,
        model=_normalization_model(model, resolved),
        pairing_mode=_resolve_pairing_mode(options),
    )
    _validate_capability(model, resolved.capabilities, normalized, options)
    provider = _resolve_api_provider_registry(registry).get_api_provider(resolved.api)
    return await call_api_provider_stream_simple(
        provider,
        model,
        normalized,
        options,
        resolved,
    )


async def complete_simple(model, context, options=None, *, registry=None):
    event_stream = await stream_simple(model, context, options, registry=registry)
    return await event_stream.result()
