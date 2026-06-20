from __future__ import annotations

import json
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from typing import Any

from loushang.ai.model.compat_schema import (
    COMPAT_DEFAULTS,
    MAX_TOKENS_FIELD,
    PROTOCOL_COMPAT_STATUS_MAPPINGS,
    REASONING_EFFORT_MAP,
    SUPPORTS_REASONING_EFFORT,
    SUPPORTS_STREAM_REASONING_DELTA,
    compat_bool,
)
from loushang.ai.model.domain import (
    ALLOWED_MODALITIES,
    Auth,
    Capabilities,
    Compat,
    Defaults,
    Endpoint,
    EndpointProtocolFeatures,
    Model,
    Pricing,
    Provider,
    SupportStatus,
)
from loushang.ai.model.registry import ModelRegistry
from loushang.ai.output_budget import default_output_tokens_from_capability

ALLOWED_COMPAT_KEYS = frozenset(COMPAT_DEFAULTS) | {
    "fineGrainedTools",
    "interleavedThinking",
    "providerTransport",
    "supportsJsonSchemaStructuredOutput",
    SUPPORTS_STREAM_REASONING_DELTA,
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
ALLOWED_PROTOCOL_KEYS = frozenset(
    {"store", "roles", "streaming", "reasoning", "tools", "cache", "session"}
)
ALLOWED_PROTOCOL_SECTION_KEYS: dict[str, frozenset[str]] = {
    "roles": frozenset({"developer"}),
    "streaming": frozenset({"usage", "reasoningDelta"}),
    "reasoning": frozenset({"effort", "effortMap", "interleaved"}),
    "tools": frozenset({"strictSchema", "eagerInputStream", "fineGrained"}),
    "cache": frozenset({"onTools", "longRetention"}),
    "session": frozenset({"idHeader", "affinityHeaders"}),
}
DEFAULT_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})


def validate_model_registry_raw(raw: dict[str, Any]) -> None:
    root = _require_mapping(raw, "<root>")
    schema_version = _schema_version(root)
    providers = _require_mapping(root.get("providers"), "providers")
    for provider_id, provider_raw in providers.items():
        provider_path = f"providers.{provider_id}"
        _validate_ref_segment_key(provider_id, provider_path)
        provider = _require_mapping(provider_raw, provider_path)
        _validate_auth_mapping(provider.get("auth"), f"{provider_path}.auth")
        endpoints = _require_mapping(
            provider.get("endpoints"), f"{provider_path}.endpoints"
        )
        for endpoint_key, endpoint_raw in endpoints.items():
            endpoint_path = f"{provider_path}.endpoints.{endpoint_key}"
            endpoint = _require_mapping(endpoint_raw, endpoint_path)
            _require_str(endpoint.get("api"), f"{endpoint_path}.api")
            _validate_optional_bool(endpoint.get("preferred"), f"{endpoint_path}.preferred")
            _validate_auth_fields(endpoint, endpoint_path)
            _validate_keyed_mapping(
                endpoint.get("compat"),
                ALLOWED_COMPAT_KEYS,
                f"{endpoint_path}.compat",
            )
            _validate_protocol_mapping(
                endpoint.get("protocol"),
                f"{endpoint_path}.protocol",
                schema_version=schema_version,
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
                _validate_auth_fields(model, model_path)
                if "protocol" in model:
                    raise ValueError(
                        "models registry field is only supported on endpoints: "
                        f"{model_path}.protocol"
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


def _schema_version(raw: dict[str, Any]) -> int:
    if "schemaVersion" not in raw:
        return DEFAULT_SCHEMA_VERSION
    value = raw["schemaVersion"]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(
            "models registry schemaVersion must be an integer: "
            "<root>.schemaVersion"
        )
    if value not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(str(version) for version in sorted(SUPPORTED_SCHEMA_VERSIONS))
        raise ValueError(
            f"unsupported models registry schemaVersion: {value}; "
            f"supported versions: {supported}"
        )
    return value


def _validate_optional_bool(value: object, path: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"models registry field must be a boolean: {path}")


def _validate_ref_segment_key(value: object, path: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"models registry key must be a non-empty string: {path}")
    if ":" in value:
        raise ValueError(
            "models registry provider and model keys must not contain ':': "
            f"{path}"
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


def _validate_auth_fields(raw: dict[str, Any], path: str) -> None:
    auth = raw.get("auth")
    legacy_auth = raw.get("authOverride")
    if auth is not None and legacy_auth is not None:
        raise ValueError(
            f"models registry field cannot define both auth and authOverride: {path}"
        )
    _validate_auth_mapping(auth, f"{path}.auth")
    _validate_auth_mapping(legacy_auth, f"{path}.authOverride")


def _validate_protocol_mapping(
    value: object,
    path: str,
    *,
    schema_version: int,
) -> None:
    if value is None:
        return
    if schema_version < 2:
        raise ValueError(
            f"models registry field requires schemaVersion 2 or newer: {path}"
        )
    mapping = _require_mapping(value, path)
    unknown = sorted(set(mapping) - ALLOWED_PROTOCOL_KEYS)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")
    if "store" in mapping:
        _validate_support_status(mapping["store"], f"{path}.store")
    for section, allowed_keys in ALLOWED_PROTOCOL_SECTION_KEYS.items():
        if section not in mapping:
            continue
        section_mapping = _require_mapping(mapping[section], f"{path}.{section}")
        section_unknown = sorted(set(section_mapping) - allowed_keys)
        if section_unknown:
            raise ValueError(
                f"models registry field has unknown keys at {path}.{section}: "
                f"{section_unknown}"
            )
        for key, entry in section_mapping.items():
            if section == "reasoning" and key == "effortMap":
                _as_optional_str_mapping(entry, f"{path}.{section}.{key}")
                continue
            _validate_support_status(entry, f"{path}.{section}.{key}")


def _validate_support_status(value: object, path: str) -> None:
    try:
        SupportStatus.from_raw(value)
    except ValueError as error:
        raise ValueError(f"models registry field has invalid support status: {path}") from error


def _validate_protocol_schema_version(raw: dict[str, Any], schema_version: int) -> None:
    if schema_version >= 2:
        return
    providers = raw.get("providers")
    if not isinstance(providers, dict):
        return
    for provider_id, provider_raw in providers.items():
        if not isinstance(provider_raw, dict):
            continue
        endpoints = provider_raw.get("endpoints")
        if not isinstance(endpoints, dict):
            continue
        for endpoint_key, endpoint_raw in endpoints.items():
            if isinstance(endpoint_raw, dict) and "protocol" in endpoint_raw:
                raise ValueError(
                    "models registry field requires schemaVersion 2 or newer: "
                    f"providers.{provider_id}.endpoints.{endpoint_key}.protocol"
                )


def _as_str_mapping(value: object, path: str) -> dict[str, str]:
    mapping = _require_mapping(value, path)
    if not all(isinstance(key, str) and isinstance(entry, str) for key, entry in mapping.items()):
        raise ValueError(f"models registry field must be a string map: {path}")
    return mapping


def _as_optional_str_mapping(value: object, path: str) -> dict[str, str | None]:
    mapping = _require_mapping(value, path)
    result: dict[str, str | None] = {}
    for key, entry in mapping.items():
        if not isinstance(key, str) or not (entry is None or isinstance(entry, str)):
            raise ValueError(
                f"models registry field must be a string-or-null map: {path}"
            )
        result[key] = entry
    return result


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
    values.update(_compat_raw_from_protocol(endpoint_raw.get("protocol")))
    return Compat(items_by_key=values)


def _status_from_legacy_bool(value: object) -> str | None:
    if not isinstance(value, bool):
        return None
    return SupportStatus.SUPPORTED.value if value else SupportStatus.UNSUPPORTED.value


def _set_protocol_status(
    raw: dict[str, object],
    section: str | None,
    key: str,
    value: object,
) -> None:
    status = _status_from_legacy_bool(value)
    if status is None:
        return
    if section is None:
        raw[key] = status
        return
    section_raw = raw.setdefault(section, {})
    if isinstance(section_raw, dict):
        section_raw[key] = status


def _set_protocol_string_or_none_mapping(
    raw: dict[str, object],
    section: str,
    key: str,
    value: object,
) -> None:
    if not isinstance(value, dict):
        return
    mapping = {
        item_key: item_value
        for item_key, item_value in value.items()
        if isinstance(item_key, str)
        and (item_value is None or isinstance(item_value, str))
    }
    if not mapping:
        return
    section_raw = raw.setdefault(section, {})
    if isinstance(section_raw, dict):
        section_raw[key] = mapping


def _compat_raw_from_protocol(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return EndpointProtocolFeatures.from_raw(value).to_compat()


def _protocol_raw_from_legacy_compat(compat: Compat) -> dict[str, object]:
    raw: dict[str, object] = {}
    for compat_key, section, protocol_key in PROTOCOL_COMPAT_STATUS_MAPPINGS:
        if compat_key in compat:
            _set_protocol_status(raw, section, protocol_key, compat[compat_key])
    if REASONING_EFFORT_MAP in compat:
        _set_protocol_string_or_none_mapping(
            raw,
            "reasoning",
            "effortMap",
            compat[REASONING_EFFORT_MAP],
        )
    return raw


def _endpoint_protocol_features(
    endpoint_raw: dict[str, Any],
    compat: Compat,
) -> EndpointProtocolFeatures:
    legacy_raw = _protocol_raw_from_legacy_compat(compat)
    explicit_raw = endpoint_raw.get("protocol")
    if isinstance(explicit_raw, dict):
        return EndpointProtocolFeatures.from_raw(_deep_merge_dict(legacy_raw, explicit_raw))
    return EndpointProtocolFeatures.from_raw(legacy_raw)


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
            endpoint_specific_auth_raw = _auth_raw(endpoint_raw)
            endpoint_auth_raw = _merge_auth_raw(
                provider_auth_raw,
                endpoint_specific_auth_raw,
            )
            endpoint_auth = Auth.from_raw(endpoint_auth_raw)
            endpoint_compat = _normalize_endpoint_compat(endpoint_raw)
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
                _auth_inherited=endpoint_specific_auth_raw is None and endpoint_auth is not None,
                protocol=_endpoint_protocol_features(endpoint_raw, endpoint_compat),
                _protocol_explicit=isinstance(endpoint_raw.get("protocol"), dict),
                compat=endpoint_compat,
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


def _load_directory_raw(path: Path) -> tuple[dict[str, Any], int] | None:
    if not path.is_dir():
        return None
    merged: dict[str, Any] = {}
    merged_schema_version = DEFAULT_SCHEMA_VERSION
    for child in sorted(path.glob("*.json")):
        raw = _load_json_file(child)
        schema_version = _schema_version(raw)
        _validate_protocol_schema_version(raw, schema_version)
        merged_schema_version = max(merged_schema_version, schema_version)
        mergeable_raw = dict(raw)
        mergeable_raw.pop("schemaVersion", None)
        merged = _deep_merge_dict(merged, mergeable_raw)
    return (merged, merged_schema_version) if merged else None


def load_layered_model_registry(
    *,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> ModelRegistry:
    raw = _load_builtin_raw()
    schema_version = _schema_version(raw)
    user_layer = _load_directory_raw(user_dir) if user_dir is not None else None
    project_layer = _load_directory_raw(project_dir) if project_dir is not None else None
    if user_layer is not None:
        user_raw, user_schema_version = user_layer
        raw = _deep_merge_dict(raw, user_raw)
        schema_version = max(schema_version, user_schema_version)
    if project_layer is not None:
        project_raw, project_schema_version = project_layer
        raw = _deep_merge_dict(raw, project_raw)
        schema_version = max(schema_version, project_schema_version)
    if schema_version != DEFAULT_SCHEMA_VERSION:
        raw["schemaVersion"] = schema_version
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
