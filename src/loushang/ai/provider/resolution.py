from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from loushang.ai.auth.support import resolve_auth_for_model
from loushang.ai.model import Model
from loushang.ai.model.compat_schema import (
    resolve_anthropic_messages_compat,
    resolve_openai_completions_compat,
    resolve_openai_responses_compat,
)
from loushang.ai.model.domain import Endpoint
from loushang.ai.model.registry import ModelRegistry, get_default_model_registry


@dataclass(frozen=True)
class ResolvedEndpoint:
    provider: str
    endpoint: str | None
    api: str
    base_url: str | None = None
    base_url_env: str | None = None
    regions: dict[str, dict] = field(default_factory=dict)
    default_region: str | None = None
    compat: dict[str, object] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedRequest:
    provider: str
    endpoint: str | None
    api: str
    base_url: str | None
    region: str | None = None
    candidate_base_urls: tuple[str, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, object] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    max_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | int | None = None


def resolve_endpoint_for_model(
    model: Model,
    *,
    catalog=None,
    registry: ModelRegistry | None = None,
) -> ResolvedEndpoint:
    del catalog
    resolved_registry = (
        registry if registry is not None else get_default_model_registry()
    )
    endpoint = resolved_registry.get_endpoint(model.provider_id, model.endpoint_id)
    return _build_resolved_endpoint(model, endpoint)


def resolve_request_for_model(
    model: Model,
    *,
    options=None,
    catalog=None,
    registry: ModelRegistry | None = None,
    env: dict[str, str] | None = None,
) -> ResolvedRequest:
    del catalog
    resolved_env = dict(os.environ) if env is None else env
    resolved_registry = (
        registry if registry is not None else get_default_model_registry()
    )
    selected_region = getattr(options, "region", None) if options is not None else None
    if not selected_region:
        selected_region = resolved_env.get("LOUSHANG_REGION")
    endpoint = _select_endpoint_for_request(
        model,
        resolved_registry,
        selected_region=selected_region,
    )
    request_model = model
    if endpoint is not None:
        endpoint_model = endpoint.get_model(model.id)
        if endpoint_model is not None:
            request_model = endpoint.bind_model(endpoint_model)
    resolved_endpoint = _build_resolved_endpoint(model, endpoint)
    base_url = _resolve_base_url(resolved_endpoint, resolved_env)
    raw_compat = dict(getattr(request_model, "compat", {}))
    defaults = dict(getattr(request_model, "defaults", {}))
    if endpoint is None or endpoint.id == model.endpoint_id:
        raw_compat.update(dict(getattr(model, "compat", {})))
        defaults.update(dict(getattr(model, "defaults", {})))
    compat = _resolve_compat_for_api(
        api=resolved_endpoint.api,
        provider_id=resolved_endpoint.provider,
        model_id=model.id,
        base_url=base_url,
        raw=raw_compat,
    )

    auth_view = resolve_auth_for_model(
        request_model,
        options=options,
        env=resolved_env,
        registry=resolved_registry,
    )
    headers = _merge_option_headers(auth_view.headers, options)
    max_tokens = _resolve_max_tokens(options, defaults)
    reasoning_effort = _resolve_reasoning_effort(options, defaults)
    temperature = _resolve_temperature(options, defaults)
    candidates = []
    if base_url:
        candidates.append(base_url)
    return ResolvedRequest(
        provider=resolved_endpoint.provider,
        endpoint=resolved_endpoint.endpoint,
        api=resolved_endpoint.api,
        base_url=base_url,
        region=resolved_endpoint.default_region,
        candidate_base_urls=tuple(candidates),
        headers=headers,
        compat=compat,
        defaults=defaults,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
    )


def _build_resolved_endpoint(
    model: Model, endpoint: Endpoint | None
) -> ResolvedEndpoint:
    if endpoint is None:
        return ResolvedEndpoint(
            provider=model.provider_id,
            endpoint=model.endpoint_id,
            api=getattr(model, "api", None) or model.endpoint_id,
            base_url=getattr(model, "base_url", None),
            base_url_env=getattr(model, "base_url_env", None),
            default_region=getattr(model, "region", None),
            compat=dict(getattr(model, "compat", {})),
            defaults=dict(getattr(model, "defaults", {})),
        )
    return ResolvedEndpoint(
        provider=endpoint.provider_id,
        endpoint=endpoint.id,
        api=endpoint.api,
        base_url=endpoint.base_url,
        base_url_env=endpoint.base_url_env,
        regions={endpoint.region: {"baseUrl": endpoint.base_url}}
        if endpoint.region and endpoint.base_url
        else {},
        default_region=endpoint.region,
        compat=dict(endpoint.compat),
        defaults=dict(endpoint.defaults),
    )


def _merge_option_headers(
    headers: dict[str, str],
    options,
) -> dict[str, str]:
    option_headers = getattr(options, "headers", None) if options is not None else None
    if not isinstance(option_headers, dict) or not option_headers:
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
    endpoint: ResolvedEndpoint,
    env: dict[str, str] | None,
) -> str | None:
    if endpoint.base_url_env:
        value = (env or {}).get(endpoint.base_url_env)
        if isinstance(value, str) and value:
            return value
    return endpoint.base_url


def _resolve_compat_for_api(
    *,
    api: str,
    provider_id: str,
    model_id: str,
    base_url: str | None,
    raw: dict[str, object],
) -> dict[str, object]:
    if api == "openai-completions":
        return resolve_openai_completions_compat(
            provider_id=provider_id,
            model_id=model_id,
            base_url=base_url,
            raw=raw,
        )
    if api == "openai-responses":
        return resolve_openai_responses_compat(raw)
    if api == "anthropic-messages":
        return resolve_anthropic_messages_compat(
            provider_id=provider_id,
            base_url=base_url,
            raw=raw,
        )
    return raw


def _resolve_max_tokens(options, defaults: dict[str, object]) -> int | None:
    value = getattr(options, "max_tokens", None) if options is not None else None
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
    value = None
    if options is not None:
        value = getattr(options, "reasoning", None) or getattr(
            options, "reasoning_effort", None
        )
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
