from __future__ import annotations

from loushang.ai.model import Capabilities
from loushang.ai.provider import ResolvedRequest, resolve_provider_request
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
    adapter_request = resolved if request is not None else None
    return start_provider_runtime(
        lambda: provider.stream_raw(
            model,
            normalized_context,
            options,
            adapter_request,
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
    if request is not None:
        return resolve_provider_request(
            provider.api,
            model,
            options=options,
            request=request,
        )
    return ResolvedRequest(
        provider=_model_value(model, "provider_id", "provider", default=provider.api),
        endpoint=_model_value(model, "endpoint_id", "endpoint", default=provider.api),
        api=_model_value(model, "api", "endpoint_id", default=provider.api),
        base_url=_model_value(model, "base_url", default=None),
        capabilities=_model_capabilities(model),
        upstream_model_id=_model_value(model, "id", default=None),
    )


def _model_value(model, *names: str, default):
    for name in names:
        value = getattr(model, name, None)
        if value is not None:
            return value
    return default


def _model_capabilities(model) -> Capabilities:
    capabilities = getattr(model, "capabilities", None)
    if isinstance(capabilities, Capabilities):
        return capabilities
    return Capabilities(
        input=tuple(getattr(model, "input", ("text",))),
        max_tokens=getattr(model, "max_tokens", None),
        reasoning=bool(getattr(model, "reasoning", False)),
        stream=True,
    )
