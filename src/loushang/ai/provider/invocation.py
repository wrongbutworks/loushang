from __future__ import annotations

import inspect
from typing import Any

from loushang.ai.context import NormalizedContext
from loushang.ai.provider.protocol import ProviderRequest
from loushang.ai.provider.runtime import start_provider_runtime


def validate_provider_invoke_raw_contract(provider: Any) -> None:
    method = getattr(provider, "invoke_raw", None)
    if not callable(method):
        raise TypeError("Provider missing required invoke_raw method")
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        raise TypeError("Provider invoke_raw signature is not inspectable") from None

    parameters = list(signature.parameters.values())
    if len(parameters) != 1:
        raise TypeError("Provider invoke_raw must accept exactly one ProviderRequest")
    parameter = parameters[0]
    if parameter.kind not in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        raise TypeError("Provider invoke_raw request must be a positional parameter")
    if parameter.name not in {"request", "provider_request"}:
        raise TypeError("Provider invoke_raw parameter must be named request")


def _call_provider_raw_parts(
    provider: Any,
    request: ProviderRequest,
):
    if not isinstance(request.context, NormalizedContext):
        raise TypeError("ProviderRequest.context must be NormalizedContext")
    return provider.invoke_raw(request)


async def call_api_provider_stream(
    provider: Any,
    request: ProviderRequest,
):
    invoke_raw_method = getattr(provider, "invoke_raw", None)
    if request.api != provider.api:
        raise ValueError(
            f"Mismatched api: provider={provider.api!r} request.api={request.api!r}"
        )
    if not callable(invoke_raw_method):
        raise TypeError("Provider missing required invoke_raw method")
    validate_provider_invoke_raw_contract(provider)
    if not isinstance(request.context, NormalizedContext):
        raise TypeError("ProviderRequest.context must be NormalizedContext")
    return start_provider_runtime(
        lambda: _call_provider_raw_parts(
            provider,
            request,
        ),
        model=request.model,
        options=request.options,
        request=request,
    )
