from __future__ import annotations

from loushang.ai.provider import (
    ProviderRequest,
    ResolvedRequest,
    resolve_provider_request,
)
from loushang.ai.provider.runtime import start_provider_runtime


def start_test_provider_stream(
    provider,
    model,
    normalized_context,
    options=None,
    *,
    request: ResolvedRequest | None = None,
):
    resolved = _runtime_request(provider, model, options=options, request=request)
    return start_provider_runtime(
        lambda: provider.stream_raw(
            ProviderRequest(
                model=model,
                context=normalized_context,
                options=options,
                resolved=resolved,
            )
        ),
        model=model,
        options=options,
        request=resolved,
    )


def _runtime_request(
    provider,
    model,
    *,
    options=None,
    request: ResolvedRequest | None = None,
) -> ResolvedRequest:
    return resolve_provider_request(
        provider.api,
        model,
        options=options,
        request=request,
        adapter_config_resolver=_adapter_config_resolver(provider),
    )


def _adapter_config_resolver(provider):
    resolver = getattr(provider, "adapter_config_resolver", None)
    return resolver if callable(resolver) else None
