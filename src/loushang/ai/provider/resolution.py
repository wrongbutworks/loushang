from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from loushang.ai.auth.support import merge_auth_config, resolve_auth_for_model
from loushang.ai.context import NormalizedContext
from loushang.ai.model import Model
from loushang.ai.model.domain import (
    AdapterConfig,
    AnthropicMessagesConfig,
    Capabilities,
    Endpoint,
    EndpointRouting,
    EndpointTransport,
    OpenAICompletionsConfig,
    OpenAIResponsesConfig,
    default_adapter_config,
    merge_adapter_config,
)
from loushang.ai.model.registry import (
    ModelRegistry,
    get_default_model_registry,
    has_bound_endpoint_context,
    resolve_model_endpoint,
)
from loushang.ai.options import get_max_output_tokens, get_reasoning_effort
from loushang.ai.provider.protocol import ProviderContext, ProviderRequest


def ensure_request_api(provider_api: str, request: ProviderRequest) -> ProviderRequest:
    if request.api != provider_api:
        raise ValueError(
            f"Mismatched api: provider={provider_api!r} request.api={request.api!r}"
        )
    return request


def normalize_provider_request_for_api(
    provider_api: str,
    request: ProviderRequest,
) -> ProviderRequest:
    request = ensure_request_api(provider_api, request)
    if provider_api == "openai-completions":
        adapter_config = _ensure_core_adapter_config(
            request.adapter_config,
            provider_api,
            OpenAICompletionsConfig,
        )
        return replace(request, adapter_config=adapter_config)
    if provider_api == "openai-responses":
        adapter_config = _ensure_core_adapter_config(
            request.adapter_config,
            provider_api,
            OpenAIResponsesConfig,
        )
        return replace(request, adapter_config=adapter_config)
    if provider_api == "anthropic-messages":
        adapter_config = _ensure_core_adapter_config(
            request.adapter_config,
            provider_api,
            AnthropicMessagesConfig,
        )
        return replace(request, adapter_config=adapter_config)
    return request


def _ensure_core_adapter_config(
    adapter_config: object | None,
    api: str,
    expected_type: type[AdapterConfig],
) -> AdapterConfig:
    if adapter_config is None:
        resolved = default_adapter_config(api)
        if resolved is None:
            raise ValueError(f"No default adapter config for api: {api}")
        return resolved
    if not isinstance(adapter_config, expected_type):
        raise TypeError(f"adapter_config for {api} must be {expected_type.__name__}")
    return adapter_config


def resolve_endpoint_for_model(
    model: Model,
    *,
    catalog=None,
    registry: ModelRegistry | None = None,
) -> Endpoint | None:
    del catalog
    resolved_registry = _registry_for_catalog_lookup(model, registry)
    endpoint = (
        resolved_registry.get_endpoint(model.provider_id, model.endpoint_id)
        if resolved_registry is not None
        else None
    )
    if endpoint is None and has_bound_endpoint_context(model):
        endpoint = resolve_model_endpoint(model)
    return endpoint


def resolve_request_for_model(
    model: Model,
    *,
    context: ProviderContext | None = None,
    options=None,
    catalog=None,
    registry: ModelRegistry | None = None,
    env: dict[str, str] | None = None,
) -> ProviderRequest:
    del catalog
    resolved_env = dict(os.environ) if env is None else env
    selected_region = getattr(options, "region", None) if options is not None else None
    if not selected_region:
        selected_region = resolved_env.get("LOUSHANG_REGION")
    resolved_registry = _registry_for_request(model, registry, selected_region)
    endpoint = (
        _select_endpoint_for_request(
            model,
            resolved_registry,
            selected_region=selected_region,
        )
        if resolved_registry is not None
        else None
    )
    if endpoint is None and has_bound_endpoint_context(model):
        endpoint = resolve_model_endpoint(model)
    request_model = model
    request_model_has_effective_context = False
    if endpoint is not None:
        endpoint_model = endpoint.get_model(model.id)
        if endpoint_model is not None:
            request_model = endpoint_model
            request_model_has_effective_context = True
    use_model_overrides = _should_apply_model_request_overrides(
        model,
        endpoint,
        request_model,
    )
    override_model = (
        model if use_model_overrides and request_model is not model else None
    )
    endpoint_context = _build_request_endpoint_context(
        request_model,
        endpoint,
        request_model=request_model,
        request_model_has_effective_context=request_model_has_effective_context,
        override_model=override_model,
    )
    base_url = _resolve_base_url(endpoint_context, resolved_env)
    defaults = dict(getattr(request_model, "defaults", {}))
    capabilities = getattr(request_model, "capabilities", Capabilities())
    adapter_config = endpoint_context["adapter_config"]
    if use_model_overrides:
        defaults.update(dict(getattr(model, "defaults", {})))
        capability_overrides = _model_capability_overrides(model)
        if capability_overrides is not None:
            capabilities = capability_overrides
        adapter_config = merge_adapter_config(
            adapter_config if isinstance(adapter_config, AdapterConfig) else None,
            getattr(model, "adapter", None),
        )
    if request_model is not model:
        capability_overrides = _model_capability_overrides(model)
        if capability_overrides is not None:
            capabilities = capability_overrides
    auth_model = _auth_model_for_request(
        model,
        endpoint,
        request_model=request_model,
        registry=resolved_registry,
    )
    auth_view = resolve_auth_for_model(
        auth_model,
        options=options,
        env=resolved_env,
    )
    headers = _merge_option_headers(auth_view.headers, options)
    auth_account_id = _auth_account_id_from_view(auth_view, headers)
    max_tokens = _resolve_max_tokens(options, defaults)
    reasoning_effort = _resolve_reasoning_effort(options, defaults)
    temperature = _resolve_temperature(options, defaults)
    candidates = []
    if base_url:
        candidates.append(base_url)
    upstream_model_id = endpoint_context["upstream_model_id"]
    return ProviderRequest(
        model=model,
        context=context or NormalizedContext(system_prompt=None),
        options=options,
        provider=str(endpoint_context["provider"]),
        endpoint=endpoint_context["endpoint"],
        api=str(endpoint_context["api"]),
        base_url=base_url,
        region=endpoint_context["default_region"],
        candidate_base_urls=tuple(candidates),
        headers=headers,
        capabilities=capabilities,
        adapter_config=adapter_config,
        defaults=defaults,
        upstream_model_id=upstream_model_id or model.id,
        transport=endpoint_context["transport"],
        routing=endpoint_context["routing"],
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        auth_account_id=auth_account_id,
    )


def _should_apply_model_request_overrides(
    model: Model,
    endpoint: Endpoint | None,
    request_model: Model,
) -> bool:
    if endpoint is None or endpoint.id == model.endpoint_id:
        return True
    return request_model is not model and not getattr(model, "api", None)


def _auth_model_for_request(
    model: Model,
    endpoint: Endpoint | None,
    *,
    request_model: Model,
    registry: ModelRegistry | None,
) -> object:
    if endpoint is None or request_model is not model:
        return request_model
    provider_auth = None
    if registry is not None:
        provider = registry.get_provider(endpoint.provider_id)
        provider_auth = getattr(provider, "auth", None)
    auth = merge_auth_config(provider_auth, endpoint.auth, getattr(model, "auth", None))
    if auth == getattr(request_model, "auth", None):
        return request_model
    if not isinstance(request_model, Model):
        return SimpleNamespace(
            provider_id=request_model.provider_id,
            endpoint_id=request_model.endpoint_id,
            id=request_model.id,
            auth=auth,
        )
    return replace(request_model, auth=auth)


def _registry_for_catalog_lookup(
    model: Model,
    registry: ModelRegistry | None,
) -> ModelRegistry | None:
    if registry is not None:
        return registry
    if has_bound_endpoint_context(model):
        return None
    return get_default_model_registry()


def _registry_for_request(
    model: Model,
    registry: ModelRegistry | None,
    selected_region: str | None,
) -> ModelRegistry | None:
    if registry is not None:
        return registry
    if not has_bound_endpoint_context(model):
        return get_default_model_registry()
    if not selected_region or selected_region == getattr(model, "region", None):
        return None
    return _matching_default_registry_for_bound_model(model)


def _matching_default_registry_for_bound_model(model: Model) -> ModelRegistry | None:
    default_registry = get_default_model_registry()
    endpoint = default_registry.get_endpoint(model.provider_id, model.endpoint_id)
    if endpoint is None or endpoint.get_model(model.id) is None:
        return None
    if endpoint.api != getattr(model, "api", None):
        return None
    if endpoint.base_url != getattr(model, "base_url", None):
        return None
    if endpoint.base_url_env != getattr(model, "base_url_env", None):
        return None
    if endpoint.region != getattr(model, "region", None):
        return None
    return default_registry


def _build_request_endpoint_context(
    model: Model,
    endpoint: Endpoint | None,
    *,
    request_model: Model | None = None,
    request_model_has_effective_context: bool = False,
    override_model: Model | None = None,
) -> dict[str, Any]:
    if endpoint is None:
        api = getattr(model, "api", None) or model.endpoint_id
        return {
            "provider": model.provider_id,
            "endpoint": model.endpoint_id,
            "api": api,
            "base_url": getattr(model, "base_url", None),
            "base_url_env": getattr(model, "base_url_env", None),
            "default_region": getattr(model, "region", None),
            "adapter_config": getattr(model, "adapter", None)
            or default_adapter_config(api),
            "defaults": dict(getattr(model, "defaults", {})),
            "upstream_model_id": _model_upstream_id(model),
            "transport": _model_transport(model),
            "routing": _model_routing(model),
        }
    transport_raw = endpoint.transport.to_raw()
    if request_model is not None:
        transport_raw = _deep_merge_raw_mapping(
            transport_raw,
            _model_transport_raw(request_model),
        )
    if override_model is not None:
        transport_raw = _deep_merge_raw_mapping(
            transport_raw,
            _model_transport_raw(override_model),
        )
    routing_raw = endpoint.routing.to_raw()
    if request_model is not None:
        routing_raw = _deep_merge_raw_mapping(
            routing_raw,
            _model_routing_raw(request_model),
        )
    if override_model is not None:
        routing_raw = _deep_merge_raw_mapping(
            routing_raw,
            _model_routing_raw(override_model),
        )
    upstream_model_id = _model_upstream_id(request_model or model)
    if override_model is not None:
        upstream_model_id = _model_upstream_id(override_model) or upstream_model_id
    endpoint_adapter_config = endpoint.adapter or default_adapter_config(endpoint.api)
    adapter_config = endpoint_adapter_config
    request_adapter = getattr(request_model or model, "adapter", None)
    if request_adapter is not None:
        if request_model_has_effective_context:
            adapter_config = request_adapter
        else:
            adapter_config = merge_adapter_config(
                endpoint_adapter_config
                if isinstance(endpoint_adapter_config, AdapterConfig)
                else None,
                request_adapter,
            )
    if (
        override_model is not None
        and getattr(override_model, "adapter", None) is not None
    ):
        adapter_config = merge_adapter_config(
            adapter_config if isinstance(adapter_config, AdapterConfig) else None,
            getattr(override_model, "adapter", None),
        )
    return {
        "provider": endpoint.provider_id,
        "endpoint": endpoint.id,
        "api": endpoint.api,
        "base_url": endpoint.base_url,
        "base_url_env": endpoint.base_url_env,
        "default_region": endpoint.region,
        "adapter_config": adapter_config,
        "defaults": dict(endpoint.defaults),
        "upstream_model_id": upstream_model_id,
        "transport": EndpointTransport.from_raw(transport_raw),
        "routing": EndpointRouting.from_raw(routing_raw),
    }


def _model_capability_overrides(model: Model) -> Capabilities | None:
    fallback = getattr(model, "capabilities", Capabilities())
    return fallback if fallback != Capabilities() else None


def _model_transport(model: Model) -> EndpointTransport:
    return EndpointTransport.from_raw(_model_transport_raw(model))


def _model_routing(model: Model) -> EndpointRouting:
    return EndpointRouting.from_raw(_model_routing_raw(model))


def _model_upstream_id(model: Model) -> str | None:
    value = getattr(model, "upstream_id", None)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _model_transport_raw(model: Model) -> dict[str, object]:
    transport = getattr(model, "transport", None)
    return transport.to_raw() if isinstance(transport, EndpointTransport) else {}


def _model_routing_raw(model: Model) -> dict[str, object]:
    routing = getattr(model, "routing", None)
    return routing.to_raw() if isinstance(routing, EndpointRouting) else {}


def _deep_merge_raw_mapping(
    base: Mapping[str, object],
    override: Mapping[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge_raw_mapping(current, value)
            continue
        merged[key] = value
    return merged


def _merge_option_headers(
    headers: dict[str, str],
    options,
) -> dict[str, str]:
    option_headers = getattr(options, "headers", None) if options is not None else None
    if not isinstance(option_headers, Mapping) or not option_headers:
        return dict(headers)
    merged = dict(headers)
    merged.update(
        {
            key: value
            for key, value in option_headers.items()
            if isinstance(key, str) and isinstance(value, str)
        }
    )
    return merged


def _auth_account_id_from_view(auth_view, headers: Mapping[str, str]) -> str | None:
    account_id = getattr(auth_view, "account_id", None)
    if not isinstance(account_id, str) or not account_id:
        return None
    auth_headers = getattr(auth_view, "headers", {}) or {}
    if _auth_material(headers) != _auth_material(auth_headers):
        return None
    return account_id


def _auth_material(headers: Mapping[str, str]) -> str | None:
    for header_name in ("authorization", "x-api-key"):
        value = _header_value(headers, header_name)
        if isinstance(value, str) and value:
            return value
    return None


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target and value:
            return value
    return None


def _select_endpoint_for_request(
    model: Model,
    registry: ModelRegistry,
    *,
    selected_region: str | None,
) -> Endpoint | None:
    endpoint = registry.get_endpoint(model.provider_id, model.endpoint_id)
    if not selected_region or endpoint is None:
        return endpoint
    if endpoint.region == selected_region:
        return endpoint
    provider = registry.get_provider(model.provider_id)
    if provider is None:
        return endpoint
    for candidate in provider.list_endpoints():
        if candidate.region != selected_region:
            continue
        if candidate.api != endpoint.api:
            continue
        if candidate.get_model(model.id) is None:
            continue
        return candidate
    return endpoint


def _resolve_base_url(
    endpoint: dict[str, Any],
    env: dict[str, str] | None,
) -> str | None:
    resolved_env = env or {}
    base_url_env = endpoint["base_url_env"]
    if base_url_env:
        value = resolved_env.get(base_url_env)
        if isinstance(value, str) and value:
            return value
    base_url = endpoint["base_url"]
    if base_url is None:
        return None
    return _expand_env_template(base_url, resolved_env)


def _expand_env_template(value: str, env: dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        replacement = env.get(name)
        if not isinstance(replacement, str) or not replacement:
            raise ValueError(
                f"Environment variable {name} is required by baseUrl template"
            )
        return replacement

    return re.sub(r"\{([A-Z_][A-Z0-9_]*)\}", _replace, value)


def _resolve_max_tokens(options, defaults: dict[str, object]) -> int | None:
    value = get_max_output_tokens(options)
    if isinstance(value, int):
        return max(1, value)
    if value is None:
        default_value = defaults.get("maxOutputTokens")
        if not isinstance(default_value, int):
            default_value = defaults.get("maxTokens")
        if isinstance(default_value, int):
            value = default_value
    return value if isinstance(value, int) else None


def _resolve_reasoning_effort(
    options,
    defaults: dict[str, Any],
) -> str | None:
    value = get_reasoning_effort(options)
    if value is None:
        default_value = defaults.get("reasoningEffort")
        if isinstance(default_value, str):
            value = default_value
    return value if isinstance(value, str) else None


def _resolve_temperature(options, defaults: dict[str, Any]) -> float | int | None:
    value = getattr(options, "temperature", None) if options is not None else None
    if value is None:
        default_value = defaults.get("temperature")
        if isinstance(default_value, int | float):
            value = default_value
    return value if isinstance(value, int | float) else None
