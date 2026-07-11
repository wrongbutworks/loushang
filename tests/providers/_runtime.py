from __future__ import annotations

from dataclasses import replace

from loushang.ai.model import (
    AdapterConfig,
    Auth,
    Capabilities,
    Defaults,
    Endpoint,
    EndpointRouting,
    EndpointTransport,
    Model,
    ModelRegistry,
    Pricing,
    Provider,
)
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
    if request is None:
        if not isinstance(model, Model) or not model.api:
            model = bound_test_model(model, api=provider.api, options=options)
        resolved = resolve_request_for_model(
            model,
            context=normalized_context,
            options=options,
        )
    else:
        resolved = request
    resolved = replace(
        resolved,
        context=normalized_context,
        options=options,
    )
    return normalize_provider_request_for_api(provider.api, resolved)


def bound_test_model(
    model: object,
    *,
    api: str,
    provider_id: str | None = None,
    endpoint_id: str | None = None,
    options: object | None = None,
    base_url: str | None = None,
    adapter_config: AdapterConfig | None = None,
    capabilities: Capabilities | None = None,
    defaults: dict[str, object] | None = None,
    transport: EndpointTransport | None = None,
    routing: EndpointRouting | None = None,
    upstream_model_id: str | None = None,
) -> Model:
    provider_id = provider_id or str(getattr(model, "provider_id", "test-provider"))
    endpoint_id = endpoint_id or str(getattr(model, "endpoint_id", api))
    model_id = str(getattr(model, "id", "test-model"))
    if capabilities is None:
        capabilities = Capabilities(
            input=tuple(getattr(model, "input", ("text",))),
            reasoning=bool(getattr(model, "reasoning", False)),
            max_tokens=getattr(model, "max_tokens", None),
        )
    pricing = getattr(model, "pricing", None)
    if not isinstance(pricing, Pricing):
        pricing = None
    auth = _test_auth(options)
    endpoint = Endpoint(
        id=endpoint_id,
        provider=provider_id,
        api=api,
        base_url=base_url if base_url is not None else getattr(model, "base_url", None),
        auth=auth,
        adapter=adapter_config,
        defaults=Defaults.from_raw(defaults or getattr(model, "defaults", None)),
        transport=transport or EndpointTransport(),
        routing=routing or EndpointRouting(),
        models={
            model_id: Model(
                id=model_id,
                provider=provider_id,
                endpoint=endpoint_id,
                capabilities=capabilities,
                pricing=pricing,
                upstream_id=upstream_model_id,
            )
        },
    )
    return ModelRegistry.from_providers(
        {
            provider_id: Provider(
                id=provider_id,
                endpoints={endpoint_id: endpoint},
            )
        }
    ).get_model(provider_id, endpoint_id, model_id)


def make_provider_request(
    model: object,
    *,
    api: str,
    provider_id: str | None = None,
    endpoint_id: str | None = None,
    options: object | None = None,
    base_url: str | None = None,
    headers: dict[str, str] | None = None,
    adapter_config: AdapterConfig | None = None,
    capabilities: Capabilities | None = None,
    defaults: dict[str, object] | None = None,
    transport: EndpointTransport | None = None,
    routing: EndpointRouting | None = None,
    upstream_model_id: str | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    temperature: float | int | None = None,
) -> ProviderRequest:
    request_model = bound_test_model(
        model,
        api=api,
        provider_id=provider_id,
        endpoint_id=endpoint_id,
        options=options,
        base_url=base_url,
        adapter_config=adapter_config,
        capabilities=capabilities,
        defaults=defaults,
        transport=transport,
        routing=routing,
        upstream_model_id=upstream_model_id,
    )
    return ProviderRequest(
        model=request_model,
        provider=request_model.provider_id,
        endpoint=request_model.endpoint_id,
        api=request_model.api,
        base_url=base_url,
        headers=dict(headers or {}),
        defaults=dict(request_model.defaults),
        transport=request_model.transport,
        routing=request_model.routing,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        upstream_model_id=request_model.upstream_id or request_model.id,
        capabilities=request_model.capabilities,
        adapter_config=request_model.adapter,
        region=request_model.region,
    )


def _test_auth(options: object | None) -> Auth:
    from loushang.ai.auth import OAuthBearerAuth

    if isinstance(getattr(options, "auth", None), OAuthBearerAuth):
        return Auth(kind="oauth")
    if getattr(options, "api_key", None) is not None:
        return Auth(kind="apiKey")
    return Auth(kind="none")
