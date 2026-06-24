from __future__ import annotations

import json
from dataclasses import replace
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any

from loushang.ai.model.domain import (
    ALLOWED_MODALITIES,
    AdapterConfig,
    Auth,
    Capabilities,
    Defaults,
    Endpoint,
    EndpointRouting,
    EndpointTransport,
    Model,
    OpenAICompletionsConfig,
    Pricing,
    Provider,
    adapter_config_allowed_keys,
    adapter_config_from_raw,
)
from loushang.ai.model.registry import ModelRegistry
from loushang.ai.output_budget import default_output_tokens_from_capability

ALLOWED_ROOT_KEYS = frozenset({"providers"})
ALLOWED_PROVIDER_KEYS = frozenset({"displayName", "website", "auth", "endpoints"})
ALLOWED_ENDPOINT_KEYS = frozenset(
    {
        "api",
        "displayName",
        "baseUrl",
        "baseUrlEnv",
        "region",
        "lane",
        "preferred",
        "docs",
        "auth",
        "authOverride",
        "adapter",
        "defaults",
        "transport",
        "routing",
        "models",
    }
)
ALLOWED_MODEL_KEYS = frozenset(
    {
        "displayName",
        "family",
        "alias",
        "knowledge",
        "releaseDate",
        "lastUpdated",
        "capabilities",
        "pricing",
        "auth",
        "authOverride",
        "adapter",
        "defaults",
        "transport",
        "routing",
        "upstreamId",
    }
)
ALLOWED_DEFAULT_KEYS = frozenset(
    {
        "contextWindow",
        "maxOutputTokens",
        "maxTokens",
        "reasoningEffort",
        "temperature",
    }
)
ALLOWED_CAPABILITY_KEYS = frozenset(
    {
        "attachment",
        "contextWindow",
        "input",
        "maxTokens",
        "output",
        "reasoning",
        "stream",
        "structuredOutput",
        "temperature",
        "toolUse",
    }
)
ALLOWED_PRICING_KEYS = frozenset(
    {"currency", "input", "output", "cacheRead", "cacheWrite"}
)
ALLOWED_AUTH_KEYS = frozenset(
    {"kind", "apiKeyEnv", "apiKeyEnvs", "header", "prefix", "extraHeaders"}
)
ALLOWED_TRANSPORT_KEYS = frozenset({"kind", "stream", "fallback", "timeout"})
ALLOWED_ROUTING_KEYS = frozenset({"requestOverrides"})
REMOVED_CATALOG_FIELDS = frozenset({"compat", "protocol", "dialect"})


def validate_model_registry_raw(raw: dict[str, Any]) -> None:
    root = _require_mapping(raw, "<root>")
    _reject_removed_field(root, "<root>", fields=frozenset({"schemaVersion"}))
    _validate_keyed_mapping(root, ALLOWED_ROOT_KEYS, "<root>")
    providers = _require_mapping(root.get("providers"), "providers")
    for provider_id, provider_raw in providers.items():
        provider_path = f"providers.{provider_id}"
        _validate_ref_segment_key(provider_id, provider_path)
        provider = _require_mapping(provider_raw, provider_path)
        _validate_keyed_mapping(provider, ALLOWED_PROVIDER_KEYS, provider_path)
        _validate_optional_str(
            provider.get("displayName"), f"{provider_path}.displayName"
        )
        _validate_optional_str(provider.get("website"), f"{provider_path}.website")
        _validate_auth_mapping(provider.get("auth"), f"{provider_path}.auth")
        endpoints = _require_mapping(
            provider.get("endpoints"), f"{provider_path}.endpoints"
        )
        for endpoint_key, endpoint_raw in endpoints.items():
            endpoint_path = f"{provider_path}.endpoints.{endpoint_key}"
            _validate_ref_segment_key(endpoint_key, endpoint_path)
            endpoint = _require_mapping(endpoint_raw, endpoint_path)
            _reject_removed_field(endpoint, endpoint_path)
            _validate_keyed_mapping(endpoint, ALLOWED_ENDPOINT_KEYS, endpoint_path)
            endpoint_api = _require_str(endpoint.get("api"), f"{endpoint_path}.api")
            _validate_optional_str(
                endpoint.get("displayName"), f"{endpoint_path}.displayName"
            )
            _validate_optional_str(endpoint.get("baseUrl"), f"{endpoint_path}.baseUrl")
            _validate_optional_str(
                endpoint.get("baseUrlEnv"), f"{endpoint_path}.baseUrlEnv"
            )
            _validate_optional_str(endpoint.get("region"), f"{endpoint_path}.region")
            _validate_optional_str(endpoint.get("lane"), f"{endpoint_path}.lane")
            _validate_optional_str(endpoint.get("docs"), f"{endpoint_path}.docs")
            _validate_optional_bool(
                endpoint.get("preferred"), f"{endpoint_path}.preferred"
            )
            _validate_auth_fields(endpoint, endpoint_path)
            _validate_adapter_mapping(
                endpoint.get("adapter"), endpoint_api, f"{endpoint_path}.adapter"
            )
            _validate_openai_compatible_endpoint_contract(
                endpoint,
                endpoint_path,
                provider_id=provider_id,
            )
            _validate_transport_mapping(
                endpoint.get("transport"), f"{endpoint_path}.transport"
            )
            _validate_routing_mapping(
                endpoint.get("routing"), f"{endpoint_path}.routing"
            )
            _validate_keyed_mapping(
                endpoint.get("defaults"),
                ALLOWED_DEFAULT_KEYS,
                f"{endpoint_path}.defaults",
            )
            models = _require_mapping(endpoint.get("models"), f"{endpoint_path}.models")
            for model_id, model_raw in models.items():
                model_path = f"{endpoint_path}.models.{model_id}"
                _validate_ref_segment_key(model_id, model_path)
                model = _require_mapping(model_raw, model_path)
                _reject_removed_field(model, model_path)
                _validate_keyed_mapping(model, ALLOWED_MODEL_KEYS, model_path)
                _validate_auth_fields(model, model_path)
                _validate_adapter_mapping(
                    model.get("adapter"), endpoint_api, f"{model_path}.adapter"
                )
                _validate_transport_mapping(
                    model.get("transport"), f"{model_path}.transport"
                )
                _validate_routing_mapping(model.get("routing"), f"{model_path}.routing")
                _validate_upstream_id(
                    model.get("upstreamId"), f"{model_path}.upstreamId"
                )
                _validate_keyed_mapping(
                    model.get("defaults"),
                    ALLOWED_DEFAULT_KEYS,
                    f"{model_path}.defaults",
                )
                _validate_pricing_mapping(model.get("pricing"), f"{model_path}.pricing")
                capabilities = _require_mapping(
                    model.get("capabilities"),
                    f"{model_path}.capabilities",
                )
                _validate_keyed_mapping(
                    capabilities,
                    ALLOWED_CAPABILITY_KEYS,
                    f"{model_path}.capabilities",
                )
                _validate_modalities(
                    capabilities.get("input"), f"{model_path}.capabilities.input"
                )
                _validate_modalities(
                    capabilities.get("output"), f"{model_path}.capabilities.output"
                )


def _require_mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"models registry field must be an object: {path}")
    return value


def _require_str(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"models registry field must be a non-empty string: {path}")
    return value


def _validate_optional_str(value: object, path: str) -> None:
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"models registry field must be a non-empty string: {path}")


def _validate_optional_bool(value: object, path: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"models registry field must be a boolean: {path}")


def _validate_bool(value: object, path: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"models registry field must be a boolean: {path}")


def _validate_positive_number(value: object, path: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"models registry field must be a positive number: {path}")


def _validate_optional_non_negative_number(value: object, path: str) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value < 0
    ):
        raise ValueError(
            f"models registry field must be a non-negative number or null: {path}"
        )


def _validate_ref_segment_key(value: object, path: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"models registry key must be a non-empty string: {path}")
    if ":" in value:
        raise ValueError(
            f"models registry provider, endpoint, and model keys must not contain ':': {path}"
        )


def _validate_keyed_mapping(
    value: object,
    allowed_keys: frozenset[str],
    path: str,
) -> None:
    if value is None:
        return
    mapping = _require_mapping(value, path)
    unknown = sorted(set(mapping) - allowed_keys)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")


def _reject_removed_field(
    mapping: dict[str, Any],
    path: str,
    *,
    fields: frozenset[str] = REMOVED_CATALOG_FIELDS,
) -> None:
    present = sorted(set(mapping) & fields)
    if present:
        raise ValueError(
            f"models registry field is no longer supported at {path}: {present}"
        )


def _validate_adapter_mapping(value: object, api: str, path: str) -> None:
    if value is None:
        return
    mapping = _require_mapping(value, path)
    allowed_keys = adapter_config_allowed_keys(api)
    if not allowed_keys:
        raise ValueError(
            f"models registry field is not supported for api {api!r}: {path}"
        )
    unknown = sorted(set(mapping) - allowed_keys)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")
    try:
        adapter_config_from_raw(api, mapping)
    except ValueError as error:
        raise ValueError(
            f"models registry field has invalid adapter config: {path}"
        ) from error


def _validate_auth_mapping(value: object, path: str) -> None:
    if value is None:
        return
    mapping = _require_mapping(value, path)
    unknown = sorted(set(mapping) - ALLOWED_AUTH_KEYS)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")
    for key in ("kind", "apiKeyEnv", "header"):
        if key in mapping:
            _require_str(mapping[key], f"{path}.{key}")
    if "prefix" in mapping and not isinstance(mapping["prefix"], str):
        raise ValueError(f"models registry field must be a string: {path}.prefix")
    api_key_envs = mapping.get("apiKeyEnvs")
    if api_key_envs is not None and (
        not isinstance(api_key_envs, list)
        or not all(isinstance(item, str) and item for item in api_key_envs)
    ):
        raise ValueError(
            f"models registry field must be a string list: {path}.apiKeyEnvs"
        )
    extra_headers = mapping.get("extraHeaders")
    if extra_headers is not None:
        _as_str_mapping(extra_headers, f"{path}.extraHeaders")


def _validate_auth_fields(raw: dict[str, Any], path: str) -> None:
    auth = raw.get("auth")
    auth_override = raw.get("authOverride")
    if auth is not None and auth_override is not None:
        raise ValueError(
            f"models registry field cannot define both auth and authOverride: {path}"
        )
    _validate_auth_mapping(auth, f"{path}.auth")
    _validate_auth_mapping(auth_override, f"{path}.authOverride")


def _validate_pricing_mapping(value: object, path: str) -> None:
    if value is None:
        return
    mapping = _require_mapping(value, path)
    unknown = sorted(set(mapping) - ALLOWED_PRICING_KEYS)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")
    if "currency" in mapping and mapping["currency"] is not None:
        _require_str(mapping["currency"], f"{path}.currency")
    for key in ("input", "output", "cacheRead", "cacheWrite"):
        if key in mapping:
            _validate_optional_non_negative_number(mapping[key], f"{path}.{key}")


def _validate_transport_mapping(value: object, path: str) -> None:
    if value is None:
        return
    mapping = _require_mapping(value, path)
    unknown = sorted(set(mapping) - ALLOWED_TRANSPORT_KEYS)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")
    for key in ("kind", "stream"):
        if key in mapping:
            _require_str(mapping[key], f"{path}.{key}")
    if "fallback" in mapping:
        _validate_bool(mapping["fallback"], f"{path}.fallback")
    if "timeout" in mapping:
        _validate_positive_number(mapping["timeout"], f"{path}.timeout")


def _validate_routing_mapping(value: object, path: str) -> None:
    if value is None:
        return
    mapping = _require_mapping(value, path)
    unknown = sorted(set(mapping) - ALLOWED_ROUTING_KEYS)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")
    if "requestOverrides" not in mapping:
        return
    overrides = _require_mapping(
        mapping["requestOverrides"], f"{path}.requestOverrides"
    )
    for key, entry in overrides.items():
        if not isinstance(key, str) or not key:
            raise ValueError(
                "models registry key must be a non-empty string: "
                f"{path}.requestOverrides"
            )
        _require_mapping(entry, f"{path}.requestOverrides.{key}")


def _validate_upstream_id(value: object, path: str) -> None:
    if value is None:
        return
    upstream_id = _require_str(value, path)
    if not upstream_id.strip():
        raise ValueError(f"models registry field must be a non-empty string: {path}")


def _validate_modalities(value: object, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item in ALLOWED_MODALITIES for item in value
    ):
        raise ValueError(f"models registry field has invalid modalities: {path}")


def _validate_openai_compatible_endpoint_contract(
    endpoint: dict[str, Any],
    path: str,
    *,
    provider_id: str,
) -> None:
    if provider_id == "openai" or endpoint.get("api") != "openai-completions":
        return
    models = endpoint.get("models")
    if not isinstance(models, dict) or not models:
        return
    if not _non_empty_str(endpoint.get("baseUrl")) and not _non_empty_str(
        endpoint.get("baseUrlEnv")
    ):
        return
    if _non_empty_mapping(endpoint.get("adapter")):
        return
    raise ValueError(
        "openai-completions endpoints for non-openai providers must declare adapter: "
        f"{path}"
    )


def _non_empty_mapping(value: object) -> bool:
    return isinstance(value, dict) and bool(value)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _as_str_mapping(value: object, path: str) -> dict[str, str]:
    mapping = _require_mapping(value, path)
    if not all(
        isinstance(key, str) and isinstance(entry, str)
        for key, entry in mapping.items()
    ):
        raise ValueError(f"models registry field must be a string map: {path}")
    return mapping


def _auth_raw(raw: dict[str, Any]) -> dict[str, Any] | None:
    value = raw.get("auth")
    if value is None:
        value = raw.get("authOverride")
    return dict(value) if isinstance(value, dict) and value else None


def _merge_auth_raw(
    base: dict[str, Any] | None,
    override: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if override is None:
        return dict(base) if base is not None else None
    if base is None:
        return dict(override)
    merged = dict(base)
    for key, value in override.items():
        if key == "extraHeaders" and isinstance(value, dict):
            existing_extra_headers = merged.get(key)
            merged[key] = {
                **dict(
                    existing_extra_headers
                    if isinstance(existing_extra_headers, dict)
                    else {}
                ),
                **value,
            }
            continue
        merged[key] = value
    return merged


def _adapter_raw(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _merged_adapter_config(
    endpoint_api: str,
    endpoint_raw: dict[str, object],
    model_raw: dict[str, object],
) -> AdapterConfig | None:
    endpoint_adapter_raw = _adapter_raw(endpoint_raw.get("adapter"))
    model_adapter_raw = _adapter_raw(model_raw.get("adapter"))
    if model_adapter_raw:
        return adapter_config_from_raw(
            endpoint_api,
            {**endpoint_adapter_raw, **model_adapter_raw},
        )
    return adapter_config_from_raw(endpoint_api, endpoint_adapter_raw)


def _overlay_nested_raw(
    base: dict[str, object],
    override: dict[str, object],
) -> dict[str, object]:
    result = dict(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = _overlay_nested_raw(existing, value)
        else:
            result[key] = value
    return result


def _derive_model_defaults(
    endpoint_api: str,
    endpoint_lane: str | None,
    endpoint_defaults: Defaults,
    raw: dict[str, Any],
    adapter: AdapterConfig | None,
) -> Defaults:
    defaults = dict(endpoint_defaults)
    defaults.update(dict(raw.get("defaults", {})))
    capabilities = Capabilities.from_raw(raw)
    max_tokens = capabilities.max_tokens
    context_window = capabilities.context_window
    supports_temperature = capabilities.temperature
    if endpoint_api == "anthropic-messages":
        defaults.setdefault(
            "maxTokens", default_output_tokens_from_capability(max_tokens)
        )
    elif endpoint_lane == "coding" and endpoint_api == "openai-completions":
        if isinstance(max_tokens, int):
            defaults.setdefault(
                "maxOutputTokens",
                default_output_tokens_from_capability(max_tokens),
            )
        if supports_temperature:
            defaults.setdefault("temperature", 0.2)
        if isinstance(adapter, OpenAICompletionsConfig) and adapter.reasoning_effort:
            defaults.setdefault("reasoningEffort", "medium")
        if isinstance(context_window, int):
            defaults.setdefault("contextWindow", context_window)
    elif endpoint_api == "openai-responses" and isinstance(max_tokens, int):
        defaults.setdefault(
            "maxOutputTokens",
            default_output_tokens_from_capability(max_tokens),
        )
    return Defaults(items_by_key=defaults)


def _derive_endpoint_id(
    endpoint_key: str,
    api: str,
    lane: str | None,
    region: str | None,
) -> str:
    if endpoint_key and ":" not in endpoint_key:
        return endpoint_key
    if lane:
        return lane
    if region and region not in {"", "global", "cn"}:
        return f"{api}-{region}"
    return api


def _build_registry(raw: dict[str, Any]) -> ModelRegistry:
    validate_model_registry_raw(raw)
    providers: dict[str, Provider] = {}
    endpoint_auth_explicit: set[tuple[str, str]] = set()
    model_auth_explicit: set[tuple[str, str, str]] = set()
    for provider_id, provider_raw in raw.get("providers", {}).items():
        provider_auth_raw = _auth_raw(provider_raw)
        provider_auth = Auth.from_raw(provider_auth_raw)
        endpoints: dict[str, Endpoint] = {}
        for endpoint_key, endpoint_raw in provider_raw.get("endpoints", {}).items():
            endpoint_api = str(endpoint_raw.get("api", ""))
            endpoint_id = _derive_endpoint_id(
                endpoint_key,
                endpoint_api,
                endpoint_raw.get("lane"),
                endpoint_raw.get("region"),
            )
            endpoint_specific_auth_raw = _auth_raw(endpoint_raw)
            if endpoint_specific_auth_raw is not None:
                endpoint_auth_explicit.add((provider_id, endpoint_id))
            effective_endpoint_auth_raw = _merge_auth_raw(
                provider_auth_raw,
                endpoint_specific_auth_raw,
            )
            endpoint_auth = Auth.from_raw(endpoint_specific_auth_raw)
            endpoint_adapter_raw = _adapter_raw(endpoint_raw.get("adapter"))
            endpoint_adapter = adapter_config_from_raw(
                endpoint_api, endpoint_adapter_raw
            )
            endpoint_transport_raw = endpoint_raw.get("transport")
            endpoint_transport = EndpointTransport.from_raw(
                endpoint_transport_raw
                if isinstance(endpoint_transport_raw, dict)
                else {}
            )
            endpoint_routing_raw = endpoint_raw.get("routing")
            endpoint_routing = EndpointRouting.from_raw(
                endpoint_routing_raw if isinstance(endpoint_routing_raw, dict) else {}
            )
            endpoint = Endpoint(
                id=endpoint_id,
                provider=provider_id,
                api=endpoint_api,
                name=endpoint_raw.get("displayName"),
                base_url=endpoint_raw.get("baseUrl"),
                base_url_env=endpoint_raw.get("baseUrlEnv"),
                region=endpoint_raw.get("region"),
                lane=endpoint_raw.get("lane"),
                preferred=bool(endpoint_raw.get("preferred", False)),
                docs=endpoint_raw.get("docs"),
                auth=endpoint_auth,
                adapter=endpoint_adapter,
                defaults=Defaults.from_raw(endpoint_raw.get("defaults")),
                transport=endpoint_transport,
                routing=endpoint_routing,
            )
            models: dict[str, Model] = {}
            for model_id, model_raw in endpoint_raw.get("models", {}).items():
                model_auth_raw = _auth_raw(model_raw)
                if model_auth_raw is not None:
                    model_auth_explicit.add((provider_id, endpoint.id, model_id))
                model_auth = Auth.from_raw(
                    _merge_auth_raw(effective_endpoint_auth_raw, model_auth_raw)
                )
                model_adapter = _merged_adapter_config(
                    endpoint.api,
                    endpoint_raw,
                    model_raw,
                )
                model_transport_raw = (
                    model_raw.get("transport")
                    if isinstance(model_raw.get("transport"), dict)
                    else {}
                )
                model_routing_raw = (
                    model_raw.get("routing")
                    if isinstance(model_raw.get("routing"), dict)
                    else {}
                )
                model_transport = EndpointTransport.from_raw(
                    _overlay_nested_raw(endpoint.transport.to_raw(), model_transport_raw)
                )
                model_routing = EndpointRouting.from_raw(
                    _overlay_nested_raw(endpoint.routing.to_raw(), model_routing_raw)
                )
                defaults = _derive_model_defaults(
                    endpoint.api,
                    endpoint.lane,
                    endpoint.defaults,
                    model_raw,
                    model_adapter,
                )
                model = Model(
                    id=model_id,
                    name=model_raw.get("displayName"),
                    provider=provider_id,
                    endpoint=endpoint.id,
                    api=endpoint.api,
                    base_url=endpoint.base_url,
                    base_url_env=endpoint.base_url_env,
                    region=endpoint.region,
                    lane=endpoint.lane,
                    preferred_endpoint=endpoint.preferred,
                    family=model_raw.get("family"),
                    alias=model_raw.get("alias"),
                    upstream_id=model_raw.get("upstreamId"),
                    capabilities=Capabilities.from_raw(model_raw),
                    knowledge=model_raw.get("knowledge"),
                    release_date=model_raw.get("releaseDate"),
                    last_updated=model_raw.get("lastUpdated"),
                    auth=model_auth,
                    pricing=Pricing.from_raw(model_raw.get("pricing")),
                    adapter=model_adapter,
                    defaults=defaults,
                    transport=model_transport,
                    routing=model_routing,
                )
                models[model_id] = model
            endpoints[endpoint.id] = Endpoint(
                id=endpoint.id,
                provider=provider_id,
                api=endpoint.api,
                name=endpoint.name,
                base_url=endpoint.base_url,
                base_url_env=endpoint.base_url_env,
                region=endpoint.region,
                lane=endpoint.lane,
                preferred=endpoint.preferred,
                docs=endpoint.docs,
                auth=endpoint.auth,
                defaults=endpoint.defaults,
                models=models,
                adapter=endpoint.adapter,
                transport=endpoint.transport,
                routing=endpoint.routing,
            )
        providers[provider_id] = Provider(
            id=provider_id,
            name=provider_raw.get("displayName"),
            website=provider_raw.get("website"),
            auth=provider_auth,
            endpoints=endpoints,
        )
    return ModelRegistry.from_providers(
        providers,
        endpoint_auth_explicit=endpoint_auth_explicit,
        model_auth_explicit=model_auth_explicit,
    )


_BUILTIN_CATALOG_RESOURCE = "models.json"


def _load_builtin_raw() -> dict[str, Any]:
    return json.loads(
        files("loushang.ai.model")
        .joinpath(_BUILTIN_CATALOG_RESOURCE)
        .read_text(encoding="utf-8")
    )


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("models registry file has invalid JSON") from error


def _build_registry_from_file(path: Path) -> ModelRegistry:
    try:
        return _build_registry(_load_json_file(path))
    except ValueError as error:
        raise ValueError(f"models registry file {path}: {error}") from error


def load_builtin_model_registry() -> ModelRegistry:
    return _build_registry(_load_builtin_raw())


def load_model_registry_from_file(path: str | Path) -> ModelRegistry:
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return _build_registry_from_file(resolved)


def load_model_registry_from_directory(path: str | Path) -> ModelRegistry:
    resolved = Path(path)
    if not resolved.is_dir():
        raise FileNotFoundError(str(resolved))
    return _combine_model_registries(_model_registry_sources_from_directory(resolved))


def _model_registry_sources_from_directory(path: Path) -> list[tuple[str, ModelRegistry]]:
    return [
        (str(child), _build_registry_from_file(child))
        for child in sorted(path.glob("*.json"))
    ]


def _provider_metadata(provider: Provider) -> Provider:
    return replace(provider, endpoints={})


def _endpoint_metadata(endpoint: Endpoint) -> Endpoint:
    return replace(endpoint, models={})


def _combine_model_registries(
    sources: list[tuple[str, ModelRegistry]],
) -> ModelRegistry:
    providers: dict[str, Provider] = {}
    endpoint_auth_explicit: set[tuple[str, str]] = set()
    model_auth_explicit: set[tuple[str, str, str]] = set()
    seen_providers: dict[str, tuple[str, str]] = {}
    seen_endpoints: dict[tuple[str, str], tuple[str, str]] = {}
    seen_models: dict[tuple[str, str, str], tuple[str, str]] = {}
    for source, registry in sources:
        endpoint_auth_explicit.update(registry._endpoint_auth_explicit)
        model_auth_explicit.update(registry._model_auth_explicit)
        for provider in registry.list_providers():
            provider_path = f"providers.{provider.id}"
            existing_provider = providers.get(provider.id)
            for endpoint in provider.list_endpoints():
                for model in endpoint.list_models():
                    model_key = (provider.id, endpoint.id, model.id)
                    field_path = (
                        f"providers.{provider.id}.endpoints.{endpoint.id}."
                        f"models.{model.id}"
                    )
                    if model_key in seen_models:
                        first_source, first_path = seen_models[model_key]
                        raise ValueError(
                            "duplicate model id "
                            f"{provider.id}:{endpoint.id}:{model.id} at "
                            f"{source}:{field_path}; first defined at "
                            f"{first_source}:{first_path}"
                        )
                    seen_models[model_key] = (source, field_path)

            if existing_provider is None:
                seen_providers[provider.id] = (source, provider_path)
            elif _provider_metadata(existing_provider) != _provider_metadata(provider):
                first_source, first_path = seen_providers[provider.id]
                raise ValueError(
                    "conflicting provider metadata "
                    f"{provider.id} at {source}:{provider_path}; "
                    f"first defined at {first_source}:{first_path}"
                )

            endpoints = dict(existing_provider.endpoints) if existing_provider else {}
            for endpoint in provider.list_endpoints():
                endpoint_key = (provider.id, endpoint.id)
                endpoint_path = f"{provider_path}.endpoints.{endpoint.id}"
                existing_endpoint = endpoints.get(endpoint.id)
                if existing_endpoint is None:
                    seen_endpoints[endpoint_key] = (source, endpoint_path)
                elif _endpoint_metadata(existing_endpoint) != _endpoint_metadata(
                    endpoint
                ):
                    first_source, first_path = seen_endpoints[endpoint_key]
                    raise ValueError(
                        "conflicting endpoint metadata "
                        f"{provider.id}:{endpoint.id} at {source}:{endpoint_path}; "
                        f"first defined at {first_source}:{first_path}"
                    )

                models = dict(existing_endpoint.models) if existing_endpoint else {}
                for model in endpoint.list_models():
                    models[model.id] = model
                if existing_endpoint is None:
                    endpoints[endpoint.id] = endpoint
                else:
                    endpoints[endpoint.id] = replace(existing_endpoint, models=models)
            if existing_provider is None:
                providers[provider.id] = replace(provider, endpoints=endpoints)
            else:
                providers[provider.id] = replace(existing_provider, endpoints=endpoints)
    return ModelRegistry.from_providers(
        providers,
        endpoint_auth_explicit=endpoint_auth_explicit,
        model_auth_explicit=model_auth_explicit,
    )


def load_layered_model_registry(
    *,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> ModelRegistry:
    sources = [("<builtin>", load_builtin_model_registry())]
    for directory in (user_dir, project_dir):
        if directory is not None and directory.is_dir():
            sources.extend(_model_registry_sources_from_directory(directory))
    return _combine_model_registries(sources)


def load_model_registry(
    path: str | Path | None = None,
) -> ModelRegistry:
    if path is None:
        return load_layered_model_registry(
            user_dir=Path.home() / ".loushang" / "models",
        )

    resolved = Path(path)
    if resolved.is_file():
        return load_model_registry_from_file(resolved)
    if resolved.is_dir():
        return load_model_registry_from_directory(resolved)
    raise FileNotFoundError(str(resolved))
