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
    resolved = provider_request_for_test(
        provider,
        model,
        normalized_context,
        options=options,
        request=request,
    )
    return start_provider_runtime(
        lambda: provider.invoke_raw(resolved),
        model=model,
        options=options,
        request=resolved,
    )


def provider_request_for_test(
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
    return normalize_provider_request_for_api(provider.api, resolved)
