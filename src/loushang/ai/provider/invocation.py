from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

from loushang.ai.context import ensure_normalized_context
from loushang.ai.options import PairingMode
from loushang.ai.provider.protocol import ProviderRequest
from loushang.ai.provider.resolution import (
    ResolvedRequest,
    resolve_provider_request,
)
from loushang.ai.provider.runtime import start_provider_runtime


def validate_provider_stream_raw_contract(provider: Any) -> None:
    method = getattr(provider, "stream_raw", None)
    if not callable(method):
        raise TypeError("Provider missing required stream_raw method")
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        raise TypeError("Provider stream_raw signature is not inspectable") from None

    parameters = list(signature.parameters.values())
    if len(parameters) != 1:
        raise TypeError("Provider stream_raw must accept exactly one ProviderRequest")
    parameter = parameters[0]
    if parameter.kind not in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        raise TypeError("Provider stream_raw request must be a positional parameter")
    if parameter.name not in {"request", "provider_request"}:
        raise TypeError("Provider stream_raw parameter must be named request")


def _resolve_pairing_mode(options) -> PairingMode:
    if options is None:
        return "strict"
    pairing_mode = getattr(options, "pairing_mode", "strict")
    if pairing_mode == "repair":
        return "repair"
    return "strict"


def _adapter_config_resolver(provider: Any):
    resolver = getattr(provider, "adapter_config_resolver", None)
    return resolver if callable(resolver) else None


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
    provider: Any,
    model,
    context,
    options,
    request: ResolvedRequest,
):
    context = _normalize_provider_context(model, context, options, request)
    return provider.stream_raw(
        ProviderRequest(
            model=model,
            context=context,
            options=options,
            resolved=request,
        )
    )


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
        adapter_config_resolver=_adapter_config_resolver(provider),
    )
    if not callable(stream_raw_method):
        if not callable(stream_method):
            raise TypeError("Provider missing required stream_raw or stream method")
        context = _normalize_provider_context(model, context, options, request)
        return await stream_method(model, context, options, request)
    validate_provider_stream_raw_contract(provider)
    return start_provider_runtime(
        lambda: _call_provider_raw_parts(
            provider,
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
        validate_provider_stream_raw_contract(provider)
        self._adapter_config_resolver = _adapter_config_resolver(provider)

    def _resolve_request(self, model, options, request: ResolvedRequest | None):
        return resolve_provider_request(
            self.api,
            model,
            options=options,
            request=request,
            adapter_config_resolver=self._adapter_config_resolver,
        )

    async def stream(
        self, model, context, options, request: ResolvedRequest | None = None
    ):
        request = self._resolve_request(model, options, request)
        return start_provider_runtime(
            lambda: _call_provider_raw_parts(
                self._provider,
                model,
                context,
                options,
                request,
            ),
            model=model,
            options=options,
            request=request,
        )
