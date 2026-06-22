from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, Literal

from loushang.ai.context import ensure_normalized_context
from loushang.ai.options import PairingMode
from loushang.ai.provider.resolution import (
    ResolvedRequest,
    resolve_provider_request,
)

_ProviderCallStyle = Literal["positional", "keyword", "legacy"]


def _provider_call_style(method: Any) -> _ProviderCallStyle:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return "legacy"

    positional_parameters: list[inspect.Parameter] = []
    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional_parameters.append(parameter)
            continue
        if (
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            and parameter.name == "request"
        ):
            return "keyword"
    request_index = (
        4
        if positional_parameters
        and positional_parameters[0].name in {"self", "cls"}
        else 3
    )
    if (
        len(positional_parameters) > request_index
        and positional_parameters[request_index].name == "request"
    ):
        return "positional"
    return "legacy"


def _resolve_pairing_mode(options) -> PairingMode:
    if options is None:
        return "strict"
    pairing_mode = getattr(options, "pairing_mode", "strict")
    if pairing_mode == "repair":
        return "repair"
    return "strict"


def normalization_model_for_request(model, request: ResolvedRequest):
    return SimpleNamespace(
        api=request.api,
        provider_id=request.provider,
        endpoint_id=getattr(request, "endpoint", getattr(model, "endpoint_id", None)),
        id=model.id,
    )


def _normalize_provider_context(model, context, options, request: ResolvedRequest):
    return ensure_normalized_context(
        context,
        model=normalization_model_for_request(model, request),
        pairing_mode=_resolve_pairing_mode(options),
    )


async def _call_provider(
    method: Any,
    style: _ProviderCallStyle,
    model,
    context,
    options,
    request: ResolvedRequest,
):
    context = _normalize_provider_context(model, context, options, request)
    if style == "legacy":
        return await method(model, context, options)
    if style == "keyword":
        return await method(model, context, options, request=request)
    return await method(model, context, options, request)


async def call_api_provider_stream(
    provider: Any,
    model,
    context,
    options,
    request: ResolvedRequest,
):
    request = resolve_provider_request(
        provider.api,
        model,
        options=options,
        request=request,
    )
    return await _call_provider(
        provider.stream,
        _provider_call_style(provider.stream),
        model,
        context,
        options,
        request,
    )


async def call_api_provider_stream_simple(
    provider: Any,
    model,
    context,
    options,
    request: ResolvedRequest,
):
    request = resolve_provider_request(
        provider.api,
        model,
        options=options,
        request=request,
    )
    return await _call_provider(
        provider.stream_simple,
        _provider_call_style(provider.stream_simple),
        model,
        context,
        options,
        request,
    )


class _RequestAwareProviderInvoker:
    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self.api = provider.api
        self._stream_style = _provider_call_style(provider.stream)
        self._stream_simple_style = _provider_call_style(provider.stream_simple)

    def _resolve_request(self, model, options, request: ResolvedRequest | None):
        return resolve_provider_request(
            self.api,
            model,
            options=options,
            request=request,
        )

    async def stream(
        self, model, context, options, request: ResolvedRequest | None = None
    ):
        request = self._resolve_request(model, options, request)
        return await _call_provider(
            self._provider.stream,
            self._stream_style,
            model,
            context,
            options,
            request,
        )

    async def stream_simple(
        self, model, context, options, request: ResolvedRequest | None = None
    ):
        request = self._resolve_request(model, options, request)
        return await _call_provider(
            self._provider.stream_simple,
            self._stream_simple_style,
            model,
            context,
            options,
            request,
        )
