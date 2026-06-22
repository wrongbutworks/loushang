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
from loushang.ai.provider.runtime import start_provider_runtime

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


def _call_provider_raw_parts(
    method: Any,
    style: _ProviderCallStyle,
    model,
    context,
    options,
    request: ResolvedRequest,
):
    context = _normalize_provider_context(model, context, options, request)
    if style == "legacy":
        return method(model, context, options)
    if style == "keyword":
        return method(model, context, options, request=request)
    return method(model, context, options, request)


async def _call_request_aware_provider(
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
    stream_method = getattr(provider, "stream", None)
    stream_raw_method = getattr(provider, "stream_raw", None)
    request = resolve_provider_request(
        provider.api,
        model,
        options=options,
        request=request,
    )
    if not callable(stream_raw_method):
        if not callable(stream_method):
            raise TypeError("Provider missing required stream_raw or stream method")
        return await _call_request_aware_provider(
            stream_method,
            _provider_call_style(stream_method),
            model,
            context,
            options,
            request,
        )
    return start_provider_runtime(
        lambda: _call_provider_raw_parts(
            stream_raw_method,
            _provider_call_style(stream_raw_method),
            model,
            context,
            options,
            request,
        ),
        model=model,
        options=options,
        request=request,
    )


class _RequestAwareProviderInvoker:
    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self.api = provider.api
        self._stream_raw_style = _provider_call_style(provider.stream_raw)

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
        return start_provider_runtime(
            lambda: _call_provider_raw_parts(
                self._provider.stream_raw,
                self._stream_raw_style,
                model,
                context,
                options,
                request,
            ),
            model=model,
            options=options,
            request=request,
        )
