from __future__ import annotations

from dataclasses import replace

from loushang.ai.provider import (
    ProviderRequest,
    normalize_provider_request_for_api,
    resolve_request_for_model,
)
from loushang.ai.provider.runtime import start_provider_runtime


def start_test_provider_stream(
    provider,
    model,
    normalized_context,
    options=None,
    *,
    request: ProviderRequest | None = None,
):
    resolved = _runtime_request(
        provider,
        model,
        normalized_context,
        options=options,
        request=request,
    )
    return start_provider_runtime(
        lambda: provider.stream_raw(resolved),
        model=model,
        options=options,
        request=resolved,
    )


def _runtime_request(
    provider,
    model,
    normalized_context,
    *,
    options=None,
    request: ProviderRequest | None = None,
) -> ProviderRequest:
    resolved = request or resolve_request_for_model(
        model,
        context=normalized_context,
        options=options,
    )
    resolved = replace(
        resolved,
        model=model,
        context=normalized_context,
        options=options,
    )
    return normalize_provider_request_for_api(
        provider.api,
        resolved,
        adapter_config_resolver=_adapter_config_resolver(provider),
    )


def _adapter_config_resolver(provider):
    resolver = getattr(provider, "adapter_config_resolver", None)
    return resolver if callable(resolver) else None
