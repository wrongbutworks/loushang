from __future__ import annotations

import json
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from typing import Any

from loushang.ai.model.compat_schema import (
    COMPAT_DEFAULTS,
    MAX_TOKENS_FIELD,
    SUPPORTS_REASONING_EFFORT,
    compat_bool,
)
from loushang.ai.model.domain import (
    ALLOWED_MODALITIES,
    Auth,
    Capabilities,
    Compat,
    Defaults,
    Endpoint,
    Model,
    Pricing,
    Provider,
)
from loushang.ai.model.registry import ModelRegistry
from loushang.ai.output_budget import default_output_tokens_from_capability

ALLOWED_COMPAT_KEYS = frozenset(COMPAT_DEFAULTS) | {
    "fineGrainedTools",
    "interleavedThinking",
    "providerTransport",
    "supportsJsonSchemaStructuredOutput",
    "supportsStreamReasoningDelta",
}
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


def validate_model_registry_raw(raw: dict[str, Any]) -> None:
    root = _require_mapping(raw, "<root>")
    providers = _require_mapping(root.get("providers"), "providers")
    for provider_id, provider_raw in providers.items():
        provider_path = f"providers.{provider_id}"
        provider = _require_mapping(provider_raw, provider_path)
        _validate_auth_mapping(provider.get("auth"), f"{provider_path}.auth")
        endpoints = _require_mapping(
            provider.get("endpoints"), f"{provider_path}.endpoints"
        )
        for endpoint_key, endpoint_raw in endpoints.items():
            endpoint_path = f"{provider_path}.endpoints.{endpoint_key}"
            endpoint = _require_mapping(endpoint_raw, endpoint_path)
            _require_str(endpoint.get("api"), f"{endpoint_path}.api")
            _validate_auth_mapping(
                endpoint.get("authOverride", endpoint.get("auth")),
                f"{endpoint_path}.auth",
            )
            _validate_keyed_mapping(
                endpoint.get("compat"),
                ALLOWED_COMPAT_KEYS,
                f"{endpoint_path}.compat",
            )
            _validate_keyed_mapping(
                endpoint.get("defaults"),
                ALLOWED_DEFAULT_KEYS,
                f"{endpoint_path}.defaults",
            )
            models = _require_mapping(endpoint.get("models"), f"{endpoint_path}.models")
            for model_id, model_raw in models.items():
                model_path = f"{endpoint_path}.models.{model_id}"
                model = _require_mapping(model_raw, model_path)
                _validate_auth_mapping(
                    model.get("authOverride", model.get("auth")),
                    f"{model_path}.auth",
                )
                _validate_keyed_mapping(
                    model.get("compat"),
                    ALLOWED_COMPAT_KEYS,
                    f"{model_path}.compat",
                )
                _validate_keyed_mapping(
                    model.get("defaults"),
                    ALLOWED_DEFAULT_KEYS,
                    f"{model_path}.defaults",
                )
                _validate_keyed_mapping(
                    model.get("pricing"),
                    ALLOWED_PRICING_KEYS,
                    f"{model_path}.pricing",
                )
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


def _validate_optional_mapping(value: object, path: str) -> None:
    if value is not None and not isinstance(value, dict):
        raise ValueError(f"models registry field must be an object: {path}")


def _require_str(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"models registry field must be a non-empty string: {path}")
    return value


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


def _validate_auth_mapping(value: object, path: str) -> None:
    if value is None:
        return
    mapping = _require_mapping(value, path)
    unknown = sorted(set(mapping) - ALLOWED_AUTH_KEYS)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")
    api_key_envs = mapping.get("apiKeyEnvs")
    if api_key_envs is not None and (
        not isinstance(api_key_envs, list)
        or not all(isinstance(item, str) for item in api_key_envs)
    ):
        raise ValueError(f"models registry field must be a string list: {path}.apiKeyEnvs")
    extra_headers = mapping.get("extraHeaders")
    if extra_headers is not None:
        _as_str_mapping(extra_headers, f"{path}.extraHeaders")


def _as_str_mapping(value: object, path: str) -> dict[str, str]:
    mapping = _require_mapping(value, path)
    if not all(isinstance(key, str) and isinstance(entry, str) for key, entry in mapping.items()):
        raise ValueError(f"models registry field must be a string map: {path}")
    return mapping


def _validate_modalities(value: object, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item in ALLOWED_MODALITIES for item in value
    ):
        raise ValueError(f"models registry field has invalid modalities: {path}")


def _normalize_endpoint_compat(endpoint_raw: dict[str, Any]) -> Compat:
    compat = Compat.from_raw(endpoint_raw.get("compat"))
    values = dict(compat)
    if str(endpoint_raw.get("api", "")) == "openai-completions":
        values.setdefault(MAX_TOKENS_FIELD, "max_completion_tokens")
    return Compat(items_by_key=values)


def _derive_model_defaults(
    endpoint_api: str,
    endpoint_lane: str | None,
    endpoint_defaults: Defaults,
    raw: dict[str, Any],
    compat: Compat,
) -> Defaults:
    defaults = dict(endpoint_defaults)
    defaults.update(dict(raw.get("defaults", {})))
    capabilities = Capabilities.from_raw(raw)
    max_tokens = capabilities.max_tokens
    context_window = capabilities.context_window
    supports_temperature = capabilities.temperature
    if endpoint_api == "anthropic-messages":
        defaults.setdefault("maxTokens", default_output_tokens_from_capability(max_tokens))
    elif endpoint_lane == "coding" and endpoint_api == "openai-completions":
        if isinstance(max_tokens, int):
            defaults.setdefault(
                "maxOutputTokens",
                default_output_tokens_from_capability(max_tokens),
            )
        if supports_temperature:
            defaults.setdefault("temperature", 0.2)
        if compat_bool(compat, SUPPORTS_REASONING_EFFORT):
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
            endpoint_auth_raw = _merge_auth_raw(
                provider_auth_raw,
                _auth_raw(endpoint_raw),
            )
            endpoint_auth = Auth.from_raw(endpoint_auth_raw)
            endpoint = Endpoint(
                id=endpoint_id,
                provider=provider_id,
                api=endpoint_api,
                name=endpoint_raw.get("displayName"),
                base_url=endpoint_raw.get("baseUrl"),
                base_url_env=endpoint_raw.get("baseUrlEnv"),
                region=endpoint_raw.get("region"),
                lane=endpoint_raw.get("lane"),
                docs=endpoint_raw.get("docs"),
                auth=endpoint_auth,
                compat=_normalize_endpoint_compat(endpoint_raw),
                defaults=Defaults.from_raw(endpoint_raw.get("defaults")),
            )
            models: dict[str, Model] = {}
            for model_id, model_raw in endpoint_raw.get("models", {}).items():
                model_auth_raw = _auth_raw(model_raw)
                model_auth = (
                    Auth.from_raw(_merge_auth_raw(endpoint_auth_raw, model_auth_raw))
                    if model_auth_raw is not None
                    else None
                )
                compat = endpoint.compat.merged(
                    Compat.from_raw(model_raw.get("compat"))
                )
                defaults = _derive_model_defaults(
                    endpoint.api,
                    endpoint.lane,
                    endpoint.defaults,
                    model_raw,
                    compat,
                )
                model = Model(
                    id=model_id,
                    name=model_raw.get("displayName"),
                    provider=provider_id,
                    endpoint=endpoint.id,
                    family=model_raw.get("family"),
                    alias=model_raw.get("alias"),
                    capabilities=Capabilities.from_raw(model_raw),
                    knowledge=model_raw.get("knowledge"),
                    release_date=model_raw.get("releaseDate"),
                    last_updated=model_raw.get("lastUpdated"),
                    auth=model_auth,
                    pricing=Pricing.from_raw(model_raw.get("pricing")),
                    compat=compat,
                    defaults=defaults,
                )
                models[model_id] = endpoint.bind_model(model)
            endpoints[endpoint.id] = replace(endpoint, models=models)
        providers[provider_id] = Provider(
            id=provider_id,
            name=provider_raw.get("displayName"),
            website=provider_raw.get("website"),
            auth=provider_auth,
            endpoints=endpoints,
        )
    return ModelRegistry.from_providers(providers)


def _auth_raw(raw: dict[str, Any]) -> dict[str, Any] | None:
    value = raw["authOverride"] if "authOverride" in raw else raw.get("auth")
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
            merged[key] = {
                **dict(merged.get(key) if isinstance(merged.get(key), dict) else {}),
                **value,
            }
            continue
        merged[key] = value
    return merged


def _load_builtin_raw() -> dict[str, Any]:
    return json.loads(
        files("loushang.ai.model").joinpath("models.json").read_text(encoding="utf-8")
    )


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_builtin_model_registry() -> ModelRegistry:
    return _build_registry(_load_builtin_raw())


def load_model_registry_from_file(path: str | Path) -> ModelRegistry:
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return _build_registry(_load_json_file(resolved))


def load_model_registry_from_directory(path: str | Path) -> ModelRegistry:
    resolved = Path(path)
    if not resolved.is_dir():
        raise FileNotFoundError(str(resolved))
    providers: dict[str, Provider] = {}
    for child in sorted(resolved.glob("*.json")):
        child_registry = _build_registry(_load_json_file(child))
        providers.update(child_registry.providers)
    return ModelRegistry.from_providers(providers)


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _load_directory_raw(path: Path) -> dict[str, Any] | None:
    if not path.is_dir():
        return None
    merged: dict[str, Any] = {}
    for child in sorted(path.glob("*.json")):
        raw = _load_json_file(child)
        merged = _deep_merge_dict(merged, raw)
    return merged if merged else None


def load_layered_model_registry(
    *,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> ModelRegistry:
    raw = _load_builtin_raw()
    user_raw = _load_directory_raw(user_dir) if user_dir is not None else None
    project_raw = _load_directory_raw(project_dir) if project_dir is not None else None
    if user_raw is not None:
        raw = _deep_merge_dict(raw, user_raw)
    if project_raw is not None:
        raw = _deep_merge_dict(raw, project_raw)
    return _build_registry(raw)


def load_model_registry(
    path: str | Path | None = None,
) -> ModelRegistry:
    if path is None:
        return load_builtin_model_registry()

    resolved = Path(path)
    if resolved.is_file():
        return load_model_registry_from_file(resolved)
    if resolved.is_dir():
        return load_model_registry_from_directory(resolved)
    raise FileNotFoundError(str(resolved))
