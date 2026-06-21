from __future__ import annotations

import json
from dataclasses import dataclass, replace
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any, Literal

from loushang.ai.model.compat_schema import (
    COMPAT_DEFAULTS,
    DIALECT_COMPAT_BOOL_MAPPINGS,
    DIALECT_COMPAT_VALUE_MAPPINGS,
    OPENROUTER_ROUTING,
    PROTOCOL_COMPAT_STATUS_MAPPINGS,
    PROVIDER_TRANSPORT,
    REASONING_EFFORT_MAP,
    SUPPORTS_JSON_SCHEMA_STRUCTURED_OUTPUT,
    SUPPORTS_PROMPT_CACHE_KEY,
    SUPPORTS_REASONING_EFFORT,
    SUPPORTS_STREAM_REASONING_DELTA,
    UPSTREAM_MODEL_ID,
    VERCEL_GATEWAY_ROUTING,
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
    EndpointRouting,
    EndpointTransport,
    EndpointWireDialect,
    Model,
    Pricing,
    Provider,
    SupportStatus,
)
from loushang.ai.model.registry import ModelRegistry
from loushang.ai.output_budget import default_output_tokens_from_capability

LEGACY_COMPAT_DIAGNOSTIC_CODE = "legacy_compat_deprecated"
LEGACY_TRANSPORT_ROUTING_COMPAT_KEYS = frozenset(
    {
        PROVIDER_TRANSPORT,
        OPENROUTER_ROUTING,
        VERCEL_GATEWAY_ROUTING,
    }
)
LEGACY_MODEL_BINDING_COMPAT_KEYS = frozenset({UPSTREAM_MODEL_ID})
LEGACY_CAPABILITY_COMPAT_KEYS = frozenset({SUPPORTS_JSON_SCHEMA_STRUCTURED_OUTPUT})
ALLOWED_ENDPOINT_COMPAT_KEYS = (
    frozenset(COMPAT_DEFAULTS)
    | LEGACY_TRANSPORT_ROUTING_COMPAT_KEYS
    | LEGACY_CAPABILITY_COMPAT_KEYS
    | {
        "fineGrainedTools",
        "interleavedThinking",
        SUPPORTS_STREAM_REASONING_DELTA,
    }
)
ALLOWED_MODEL_COMPAT_KEYS = (
    ALLOWED_ENDPOINT_COMPAT_KEYS | LEGACY_MODEL_BINDING_COMPAT_KEYS
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
ALLOWED_PROTOCOL_KEYS = frozenset(
    {"store", "roles", "streaming", "reasoning", "tools", "cache", "session"}
)
ALLOWED_PROTOCOL_SECTION_KEYS: dict[str, frozenset[str]] = {
    "roles": frozenset({"developer"}),
    "streaming": frozenset({"usage", "reasoningDelta"}),
    "reasoning": frozenset({"effort", "effortMap", "interleaved"}),
    "tools": frozenset({"strictSchema", "eagerInputStream", "fineGrained"}),
    "cache": frozenset({"onTools", "longRetention", "promptKey"}),
    "session": frozenset({"idHeader", "affinityHeaders"}),
}
ALLOWED_DIALECT_KEYS = frozenset(
    {"maxOutputTokensField", "tools", "reasoning", "cache"}
)
ALLOWED_DIALECT_SECTION_KEYS: dict[str, frozenset[str]] = {
    "tools": frozenset({"resultNameRequired", "assistantBridgeRequired", "streamFlag"}),
    "reasoning": frozenset(
        {"wireFormat", "thinkingAsText", "assistantContentRequired"}
    ),
    "cache": frozenset({"controlFormat"}),
}
ALLOWED_TRANSPORT_KEYS = frozenset({"kind", "stream", "fallback", "timeout"})
ALLOWED_ROUTING_KEYS = frozenset({"requestOverrides"})
DEFAULT_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})


def _nested_target(prefix: str, section: str | None, key: str) -> str:
    return f"{prefix}.{key}" if section is None else f"{prefix}.{section}.{key}"


LEGACY_COMPAT_TRANSLATION_TARGETS: dict[str, str] = {
    **{
        compat_key: _nested_target("protocol", section, target_key)
        for compat_key, section, target_key in PROTOCOL_COMPAT_STATUS_MAPPINGS
    },
    REASONING_EFFORT_MAP: "protocol.reasoning.effortMap",
    **{
        compat_key: _nested_target("dialect", section, target_key)
        for compat_key, section, target_key in DIALECT_COMPAT_BOOL_MAPPINGS
    },
    **{
        compat_key: _nested_target("dialect", section, target_key)
        for compat_key, section, target_key in DIALECT_COMPAT_VALUE_MAPPINGS
    },
    OPENROUTER_ROUTING: "routing.requestOverrides.openrouter",
    VERCEL_GATEWAY_ROUTING: "routing.requestOverrides.vercelGateway",
    PROVIDER_TRANSPORT: "transport.kind",
    SUPPORTS_JSON_SCHEMA_STRUCTURED_OUTPUT: "capabilities.structuredOutput",
    UPSTREAM_MODEL_ID: "model.upstreamId",
}
DEPRECATED_LEGACY_COMPAT_KEYS = frozenset(LEGACY_COMPAT_TRANSLATION_TARGETS)
MODEL_LEVEL_DEPRECATED_LEGACY_COMPAT_KEYS = (
    LEGACY_TRANSPORT_ROUTING_COMPAT_KEYS
    | LEGACY_MODEL_BINDING_COMPAT_KEYS
    | LEGACY_CAPABILITY_COMPAT_KEYS
)


@dataclass(frozen=True)
class ModelRegistryLoadDiagnostic:
    code: str
    path: str
    legacy_key: str
    target: str
    message: str
    level: Literal["warning"] = "warning"


@dataclass(frozen=True)
class ModelRegistryLoadResult:
    registry: ModelRegistry
    diagnostics: tuple[ModelRegistryLoadDiagnostic, ...] = ()


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
            _validate_optional_bool(
                endpoint.get("preferred"), f"{endpoint_path}.preferred"
            )
            _validate_auth_fields(endpoint, endpoint_path)
            _validate_compat_mapping(
                endpoint.get("compat"),
                ALLOWED_ENDPOINT_COMPAT_KEYS,
                f"{endpoint_path}.compat",
            )
            _validate_protocol_mapping(
                endpoint.get("protocol"),
                f"{endpoint_path}.protocol",
                schema_version=schema_version,
            )
            _validate_dialect_mapping(
                endpoint.get("dialect"),
                f"{endpoint_path}.dialect",
                schema_version=schema_version,
            )
            _validate_transport_mapping(
                endpoint.get("transport"),
                f"{endpoint_path}.transport",
                schema_version=schema_version,
            )
            _validate_routing_mapping(
                endpoint.get("routing"),
                f"{endpoint_path}.routing",
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
                if "dialect" in model:
                    raise ValueError(
                        "models registry field is only supported on endpoints: "
                        f"{model_path}.dialect"
                    )
                _validate_transport_mapping(
                    model.get("transport"),
                    f"{model_path}.transport",
                    schema_version=schema_version,
                )
                _validate_routing_mapping(
                    model.get("routing"),
                    f"{model_path}.routing",
                    schema_version=schema_version,
                )
                _validate_upstream_id(
                    model.get("upstreamId"),
                    f"{model_path}.upstreamId",
                    schema_version=schema_version,
                )
                _validate_compat_mapping(
                    model.get("compat"),
                    ALLOWED_MODEL_COMPAT_KEYS,
                    f"{model_path}.compat",
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
            "models registry schemaVersion must be an integer: <root>.schemaVersion"
        )
    if value not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(
            str(version) for version in sorted(SUPPORTED_SCHEMA_VERSIONS)
        )
        raise ValueError(
            f"unsupported models registry schemaVersion: {value}; "
            f"supported versions: {supported}"
        )
    return value


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
            f"models registry provider and model keys must not contain ':': {path}"
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


def _validate_compat_mapping(
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
    bool_keys = {
        compat_key for compat_key, _, _ in PROTOCOL_COMPAT_STATUS_MAPPINGS
    } | {compat_key for compat_key, _, _ in DIALECT_COMPAT_BOOL_MAPPINGS}
    bool_keys.update(
        {
            SUPPORTS_JSON_SCHEMA_STRUCTURED_OUTPUT,
            SUPPORTS_PROMPT_CACHE_KEY,
        }
    )
    value_keys = {
        compat_key for compat_key, _, _ in DIALECT_COMPAT_VALUE_MAPPINGS
    }
    for key, entry in mapping.items():
        entry_path = f"{path}.{key}"
        if key in bool_keys:
            _validate_bool(entry, entry_path)
        elif key == REASONING_EFFORT_MAP:
            _as_optional_str_mapping(entry, entry_path)
        elif key in value_keys:
            if key in {"thinkingFormat", "cacheControlFormat"} and entry is None:
                continue
            _require_str(entry, entry_path)
        elif key in {PROVIDER_TRANSPORT, UPSTREAM_MODEL_ID}:
            _require_str(entry, entry_path)


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
        raise ValueError(
            f"models registry field must be a string list: {path}.apiKeyEnvs"
        )
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


def _validate_dialect_mapping(
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
    unknown = sorted(set(mapping) - ALLOWED_DIALECT_KEYS)
    if unknown:
        raise ValueError(f"models registry field has unknown keys at {path}: {unknown}")
    if "maxOutputTokensField" in mapping:
        _require_str(mapping["maxOutputTokensField"], f"{path}.maxOutputTokensField")
    for section, allowed_keys in ALLOWED_DIALECT_SECTION_KEYS.items():
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
            if key in {"wireFormat", "controlFormat"}:
                _require_str(entry, f"{path}.{section}.{key}")
                continue
            _validate_bool(entry, f"{path}.{section}.{key}")


def _validate_transport_mapping(
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


def _validate_routing_mapping(
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


def _validate_upstream_id(
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
    upstream_id = _require_str(value, path)
    if not upstream_id.strip():
        raise ValueError(f"models registry field must be a non-empty string: {path}")


def _validate_support_status(value: object, path: str) -> None:
    try:
        SupportStatus.from_raw(value)
    except ValueError as error:
        raise ValueError(
            f"models registry field has invalid support status: {path}"
        ) from error


def _validate_typed_schema_version(
    raw: dict[str, Any],
    schema_version: int,
) -> None:
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
            if not isinstance(endpoint_raw, dict):
                continue
            for field in ("protocol", "dialect", "transport", "routing"):
                if field in endpoint_raw:
                    raise ValueError(
                        "models registry field requires schemaVersion 2 or newer: "
                        f"providers.{provider_id}.endpoints.{endpoint_key}.{field}"
                    )
            models = endpoint_raw.get("models")
            if not isinstance(models, dict):
                continue
            for model_id, model_raw in models.items():
                if not isinstance(model_raw, dict):
                    continue
                for field in ("transport", "routing", "upstreamId"):
                    if field in model_raw:
                        raise ValueError(
                            "models registry field requires schemaVersion 2 or newer: "
                            f"providers.{provider_id}.endpoints."
                            f"{endpoint_key}.models.{model_id}.{field}"
                        )


def _as_str_mapping(value: object, path: str) -> dict[str, str]:
    mapping = _require_mapping(value, path)
    if not all(
        isinstance(key, str) and isinstance(entry, str)
        for key, entry in mapping.items()
    ):
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
    values = {
        key: value
        for key, value in compat.items()
        if key
        not in LEGACY_TRANSPORT_ROUTING_COMPAT_KEYS | LEGACY_MODEL_BINDING_COMPAT_KEYS
    }
    values.update(_compat_raw_from_protocol(endpoint_raw.get("protocol")))
    values.update(_compat_raw_from_dialect(endpoint_raw.get("dialect")))
    return Compat(items_by_key=values)


def _normalize_model_compat(model_raw: dict[str, Any]) -> Compat:
    compat = Compat.from_raw(model_raw.get("compat"))
    return Compat(
        items_by_key={
            key: value
            for key, value in compat.items()
            if key
            not in LEGACY_TRANSPORT_ROUTING_COMPAT_KEYS
            | LEGACY_MODEL_BINDING_COMPAT_KEYS
        }
    )


def _legacy_structured_output_value(compat: Compat) -> bool | None:
    value = compat.get(SUPPORTS_JSON_SCHEMA_STRUCTURED_OUTPUT)
    return value if isinstance(value, bool) else None


def _model_has_typed_structured_output(model_raw: dict[str, Any]) -> bool:
    capabilities_raw = model_raw.get("capabilities")
    if isinstance(capabilities_raw, dict):
        return "structuredOutput" in capabilities_raw
    return "structuredOutput" in model_raw


def _model_capabilities_from_raw(
    model_raw: dict[str, Any],
    *,
    model_legacy_compat: Compat,
    endpoint_legacy_compat: Compat,
) -> Capabilities:
    if _model_has_typed_structured_output(model_raw):
        return Capabilities.from_raw(model_raw)
    value = _legacy_structured_output_value(model_legacy_compat)
    if value is None:
        value = _legacy_structured_output_value(endpoint_legacy_compat)
    if value is None:
        return Capabilities.from_raw(model_raw)
    capabilities_raw = model_raw.get("capabilities")
    if isinstance(capabilities_raw, dict):
        merged_capabilities = dict(capabilities_raw)
        merged_capabilities["structuredOutput"] = value
        return Capabilities.from_raw({**model_raw, "capabilities": merged_capabilities})
    return Capabilities.from_raw({**model_raw, "structuredOutput": value})


def _model_compat_with_effective_capabilities(
    compat: Compat,
    capabilities: Capabilities,
) -> Compat:
    if SUPPORTS_JSON_SCHEMA_STRUCTURED_OUTPUT not in compat:
        return compat
    values = compat.to_raw()
    values[SUPPORTS_JSON_SCHEMA_STRUCTURED_OUTPUT] = capabilities.structured_output
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


def _set_dialect_bool(
    raw: dict[str, object],
    section: str,
    key: str,
    value: object,
) -> None:
    if not isinstance(value, bool):
        return
    section_raw = raw.setdefault(section, {})
    if isinstance(section_raw, dict):
        section_raw[key] = value


def _set_dialect_value(
    raw: dict[str, object],
    section: str | None,
    key: str,
    value: object,
) -> None:
    if not isinstance(value, str) or not value:
        return
    if section is None:
        raw[key] = value
        return
    section_raw = raw.setdefault(section, {})
    if isinstance(section_raw, dict):
        section_raw[key] = value


def _compat_raw_from_protocol(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return EndpointProtocolFeatures.from_raw(value).to_compat()


def _compat_raw_from_dialect(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return EndpointWireDialect.from_raw(value).to_compat()


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


def _dialect_raw_from_legacy_compat(compat: Compat) -> dict[str, object]:
    raw: dict[str, object] = {}
    for compat_key, section, dialect_key in DIALECT_COMPAT_BOOL_MAPPINGS:
        if compat_key in compat:
            _set_dialect_bool(raw, section, dialect_key, compat[compat_key])
    for compat_key, value_section, dialect_key in DIALECT_COMPAT_VALUE_MAPPINGS:
        if compat_key in compat:
            _set_dialect_value(raw, value_section, dialect_key, compat[compat_key])
    return raw


def _transport_raw_from_legacy_compat(compat: Compat) -> dict[str, object]:
    raw: dict[str, object] = {}
    value = compat.get(PROVIDER_TRANSPORT)
    if isinstance(value, str) and value:
        raw["kind"] = value
    return raw


def _transport_compat_raw_from_legacy_compat(compat: Compat) -> dict[str, object]:
    value = compat.get(PROVIDER_TRANSPORT)
    if isinstance(value, str) and value:
        return {PROVIDER_TRANSPORT: value}
    return {}


def _routing_raw_from_legacy_compat(compat: Compat) -> dict[str, object]:
    request_overrides: dict[str, object] = {}
    for compat_key, routing_key in (
        (OPENROUTER_ROUTING, "openrouter"),
        (VERCEL_GATEWAY_ROUTING, "vercelGateway"),
    ):
        value = compat.get(compat_key)
        if isinstance(value, dict) and value:
            request_overrides[routing_key] = dict(value)
    if not request_overrides:
        return {}
    return {"requestOverrides": request_overrides}


def _routing_compat_raw_from_legacy_compat(compat: Compat) -> dict[str, object]:
    raw: dict[str, object] = {}
    for compat_key in (OPENROUTER_ROUTING, VERCEL_GATEWAY_ROUTING):
        value = compat.get(compat_key)
        if isinstance(value, dict) and value:
            raw[compat_key] = dict(value)
    return raw


def _upstream_id_from_legacy_compat(compat: Compat) -> str | None:
    value = compat.get(UPSTREAM_MODEL_ID)
    return value if isinstance(value, str) and value.strip() else None


def _upstream_id_compat_raw_from_legacy_compat(compat: Compat) -> dict[str, object]:
    value = _upstream_id_from_legacy_compat(compat)
    return {UPSTREAM_MODEL_ID: value} if value is not None else {}


def _model_upstream_id(
    model_raw: dict[str, Any],
    compat: Compat,
) -> str | None:
    explicit = model_raw.get("upstreamId")
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    return _upstream_id_from_legacy_compat(compat)


def _endpoint_protocol_features(
    endpoint_raw: dict[str, Any],
    compat: Compat,
) -> EndpointProtocolFeatures:
    legacy_raw = _protocol_raw_from_legacy_compat(compat)
    explicit_raw = endpoint_raw.get("protocol")
    if isinstance(explicit_raw, dict):
        return EndpointProtocolFeatures.from_raw(
            _deep_merge_dict(legacy_raw, explicit_raw)
        )
    return EndpointProtocolFeatures.from_raw(legacy_raw)


def _endpoint_wire_dialect(
    endpoint_raw: dict[str, Any],
    compat: Compat,
) -> EndpointWireDialect:
    legacy_raw = _dialect_raw_from_legacy_compat(compat)
    explicit_raw = endpoint_raw.get("dialect")
    if isinstance(explicit_raw, dict):
        return EndpointWireDialect.from_raw(_deep_merge_dict(legacy_raw, explicit_raw))
    return EndpointWireDialect.from_raw(legacy_raw)


def _endpoint_transport(
    endpoint_raw: dict[str, Any],
    compat: Compat,
) -> EndpointTransport:
    legacy_raw = _transport_raw_from_legacy_compat(compat)
    explicit_raw = endpoint_raw.get("transport")
    if isinstance(explicit_raw, dict):
        return EndpointTransport.from_raw(_deep_merge_dict(legacy_raw, explicit_raw))
    return EndpointTransport.from_raw(legacy_raw)


def _endpoint_routing(
    endpoint_raw: dict[str, Any],
    compat: Compat,
) -> EndpointRouting:
    legacy_raw = _routing_raw_from_legacy_compat(compat)
    explicit_raw = endpoint_raw.get("routing")
    if isinstance(explicit_raw, dict):
        return EndpointRouting.from_raw(_deep_merge_dict(legacy_raw, explicit_raw))
    return EndpointRouting.from_raw(legacy_raw)


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


def _legacy_compat_diagnostics(
    raw: dict[str, Any],
    path: str,
    *,
    location: Literal["endpoint", "model"],
) -> tuple[ModelRegistryLoadDiagnostic, ...]:
    compat_raw = raw.get("compat")
    if not isinstance(compat_raw, dict):
        return ()
    diagnostics: list[ModelRegistryLoadDiagnostic] = []
    for legacy_key in sorted(compat_raw):
        target = _legacy_compat_diagnostic_target(legacy_key, location=location)
        if target is None:
            continue
        diagnostics.append(
            ModelRegistryLoadDiagnostic(
                code=LEGACY_COMPAT_DIAGNOSTIC_CODE,
                path=f"{path}.compat.{legacy_key}",
                legacy_key=legacy_key,
                target=target,
                message=(
                    f"Legacy compat key {legacy_key!r} maps to {target!r}; "
                    "write the typed catalog field instead."
                ),
            )
        )
    return tuple(diagnostics)


def _legacy_compat_diagnostic_target(
    legacy_key: str,
    *,
    location: Literal["endpoint", "model"],
) -> str | None:
    if legacy_key not in DEPRECATED_LEGACY_COMPAT_KEYS:
        return None
    if (
        location == "model"
        and legacy_key not in MODEL_LEVEL_DEPRECATED_LEGACY_COMPAT_KEYS
    ):
        return None
    return LEGACY_COMPAT_TRANSLATION_TARGETS[legacy_key]


def _legacy_compat_diagnostics_by_provider(
    raw: dict[str, Any],
) -> dict[str, tuple[ModelRegistryLoadDiagnostic, ...]]:
    providers_raw = raw.get("providers")
    if not isinstance(providers_raw, dict):
        return {}
    diagnostics_by_provider: dict[str, tuple[ModelRegistryLoadDiagnostic, ...]] = {}
    for provider_id, provider_raw in providers_raw.items():
        if not isinstance(provider_id, str) or not isinstance(provider_raw, dict):
            continue
        provider_path = f"providers.{provider_id}"
        provider_diagnostics: list[ModelRegistryLoadDiagnostic] = []
        endpoints_raw = provider_raw.get("endpoints")
        if not isinstance(endpoints_raw, dict):
            continue
        for endpoint_key, endpoint_raw in endpoints_raw.items():
            if not isinstance(endpoint_key, str) or not isinstance(endpoint_raw, dict):
                continue
            endpoint_path = f"{provider_path}.endpoints.{endpoint_key}"
            provider_diagnostics.extend(
                _legacy_compat_diagnostics(
                    endpoint_raw,
                    endpoint_path,
                    location="endpoint",
                )
            )
            models_raw = endpoint_raw.get("models")
            if not isinstance(models_raw, dict):
                continue
            for model_id, model_raw in models_raw.items():
                if not isinstance(model_id, str) or not isinstance(model_raw, dict):
                    continue
                model_path = f"{endpoint_path}.models.{model_id}"
                provider_diagnostics.extend(
                    _legacy_compat_diagnostics(
                        model_raw,
                        model_path,
                        location="model",
                    )
                )
        diagnostics_by_provider[provider_id] = tuple(provider_diagnostics)
    return diagnostics_by_provider


def _build_registry_result(raw: dict[str, Any]) -> ModelRegistryLoadResult:
    validate_model_registry_raw(raw)
    schema_version = _schema_version(raw)
    diagnostics: list[ModelRegistryLoadDiagnostic] = []
    providers: dict[str, Provider] = {}
    for provider_id, provider_raw in raw.get("providers", {}).items():
        provider_path = f"providers.{provider_id}"
        provider_auth_raw = _auth_raw(provider_raw)
        provider_auth = Auth.from_raw(provider_auth_raw)
        endpoints: dict[str, Endpoint] = {}
        for endpoint_key, endpoint_raw in provider_raw.get("endpoints", {}).items():
            endpoint_path = f"{provider_path}.endpoints.{endpoint_key}"
            diagnostics.extend(
                _legacy_compat_diagnostics(
                    endpoint_raw,
                    endpoint_path,
                    location="endpoint",
                )
            )
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
            endpoint_legacy_compat = Compat.from_raw(endpoint_raw.get("compat"))
            endpoint_compat = _normalize_endpoint_compat(endpoint_raw)
            endpoint_dialect_raw = endpoint_raw.get("dialect")
            endpoint_dialect = _endpoint_wire_dialect(endpoint_raw, endpoint_compat)
            endpoint_transport_raw = endpoint_raw.get("transport")
            endpoint_transport_legacy_raw = _transport_raw_from_legacy_compat(
                endpoint_legacy_compat
            )
            endpoint_transport_legacy_compat_raw = (
                _transport_compat_raw_from_legacy_compat(endpoint_legacy_compat)
            )
            endpoint_transport = _endpoint_transport(
                endpoint_raw,
                endpoint_legacy_compat,
            )
            endpoint_transport_legacy_source = (
                endpoint_transport_legacy_compat_raw
                if schema_version < 2
                and not isinstance(endpoint_transport_raw, dict)
                and endpoint_transport_legacy_compat_raw
                else None
            )
            endpoint_routing_raw = endpoint_raw.get("routing")
            endpoint_routing_legacy_raw = _routing_raw_from_legacy_compat(
                endpoint_legacy_compat
            )
            endpoint_routing_legacy_compat_raw = _routing_compat_raw_from_legacy_compat(
                endpoint_legacy_compat
            )
            endpoint_routing = _endpoint_routing(
                endpoint_raw,
                endpoint_legacy_compat,
            )
            endpoint_routing_legacy_source = (
                endpoint_routing_legacy_compat_raw
                if schema_version < 2
                and not isinstance(endpoint_routing_raw, dict)
                and endpoint_routing_legacy_compat_raw
                else None
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
                _auth_inherited=endpoint_specific_auth_raw is None
                and endpoint_auth is not None,
                protocol=_endpoint_protocol_features(endpoint_raw, endpoint_compat),
                _protocol_explicit=isinstance(endpoint_raw.get("protocol"), dict),
                dialect=endpoint_dialect,
                _dialect_explicit=isinstance(endpoint_dialect_raw, dict),
                _dialect_raw=dict(endpoint_dialect_raw)
                if isinstance(endpoint_dialect_raw, dict)
                else None,
                _dialect_raw_source=endpoint_dialect
                if isinstance(endpoint_dialect_raw, dict)
                else None,
                transport=endpoint_transport,
                _transport_explicit=isinstance(endpoint_transport_raw, dict)
                or (schema_version >= 2 and bool(endpoint_transport_legacy_raw)),
                _transport_raw=dict(endpoint_transport_raw)
                if isinstance(endpoint_transport_raw, dict)
                else None,
                _transport_raw_source=endpoint_transport
                if isinstance(endpoint_transport_raw, dict)
                and not endpoint_transport_legacy_raw
                else None,
                _transport_legacy_raw=endpoint_transport_legacy_source,
                routing=endpoint_routing,
                _routing_explicit=isinstance(endpoint_routing_raw, dict)
                or (schema_version >= 2 and bool(endpoint_routing_legacy_raw)),
                _routing_raw=dict(endpoint_routing_raw)
                if isinstance(endpoint_routing_raw, dict)
                else None,
                _routing_raw_source=endpoint_routing
                if isinstance(endpoint_routing_raw, dict)
                and not endpoint_routing_legacy_raw
                else None,
                _routing_legacy_raw=endpoint_routing_legacy_source,
                compat=endpoint_compat,
                defaults=Defaults.from_raw(endpoint_raw.get("defaults")),
            )
            models: dict[str, Model] = {}
            for model_id, model_raw in endpoint_raw.get("models", {}).items():
                model_path = f"{endpoint_path}.models.{model_id}"
                diagnostics.extend(
                    _legacy_compat_diagnostics(
                        model_raw,
                        model_path,
                        location="model",
                    )
                )
                model_auth_raw = _auth_raw(model_raw)
                model_auth = (
                    Auth.from_raw(_merge_auth_raw(endpoint_auth_raw, model_auth_raw))
                    if model_auth_raw is not None
                    else None
                )
                model_legacy_compat = Compat.from_raw(model_raw.get("compat"))
                model_upstream_id = _model_upstream_id(model_raw, model_legacy_compat)
                model_upstream_legacy_raw = _upstream_id_compat_raw_from_legacy_compat(
                    model_legacy_compat
                )
                model_upstream_legacy_source = (
                    model_upstream_legacy_raw
                    if schema_version < 2
                    and "upstreamId" not in model_raw
                    and model_upstream_legacy_raw
                    else None
                )
                model_transport_raw = (
                    model_raw.get("transport")
                    if isinstance(model_raw.get("transport"), dict)
                    else {}
                )
                model_transport_legacy_raw = _transport_raw_from_legacy_compat(
                    model_legacy_compat
                )
                model_transport_legacy_compat_raw = (
                    _transport_compat_raw_from_legacy_compat(model_legacy_compat)
                )
                model_transport = EndpointTransport.from_raw(
                    _deep_merge_dict(
                        model_transport_legacy_raw,
                        model_transport_raw,
                    )
                )
                model_transport_legacy_source = (
                    model_transport_legacy_compat_raw
                    if schema_version < 2
                    and not model_transport_raw
                    and model_transport_legacy_compat_raw
                    else None
                )
                model_routing_raw = (
                    model_raw.get("routing")
                    if isinstance(model_raw.get("routing"), dict)
                    else {}
                )
                model_routing_legacy_raw = _routing_raw_from_legacy_compat(
                    model_legacy_compat
                )
                model_routing_legacy_compat_raw = (
                    _routing_compat_raw_from_legacy_compat(model_legacy_compat)
                )
                model_routing = EndpointRouting.from_raw(
                    _deep_merge_dict(
                        model_routing_legacy_raw,
                        model_routing_raw,
                    )
                )
                model_routing_legacy_source = (
                    model_routing_legacy_compat_raw
                    if schema_version < 2
                    and not model_routing_raw
                    and model_routing_legacy_compat_raw
                    else None
                )
                capabilities = _model_capabilities_from_raw(
                    model_raw,
                    model_legacy_compat=model_legacy_compat,
                    endpoint_legacy_compat=endpoint_legacy_compat,
                )
                compat = _model_compat_with_effective_capabilities(
                    endpoint.compat.merged(_normalize_model_compat(model_raw)),
                    capabilities,
                )
                model_own_compat = _model_compat_with_effective_capabilities(
                    _normalize_model_compat(model_raw),
                    capabilities,
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
                    upstream_id=model_upstream_id,
                    _upstream_id_legacy_raw=model_upstream_legacy_source,
                    capabilities=capabilities,
                    knowledge=model_raw.get("knowledge"),
                    release_date=model_raw.get("releaseDate"),
                    last_updated=model_raw.get("lastUpdated"),
                    auth=model_auth,
                    pricing=Pricing.from_raw(model_raw.get("pricing")),
                    compat=compat,
                    defaults=defaults,
                    transport=model_transport,
                    _transport_own_raw=None
                    if model_transport_legacy_source is not None
                    else model_transport.to_raw(),
                    _transport_legacy_raw=model_transport_legacy_source,
                    routing=model_routing,
                    _routing_own_raw=None
                    if model_routing_legacy_source is not None
                    else model_routing.to_raw(),
                    _routing_legacy_raw=model_routing_legacy_source,
                ).with_contract_overrides(
                    compat=model_own_compat,
                    capabilities=capabilities,
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
    return ModelRegistryLoadResult(
        registry=ModelRegistry.from_providers(providers),
        diagnostics=tuple(diagnostics),
    )


def _build_registry(raw: dict[str, Any]) -> ModelRegistry:
    return _build_registry_result(raw).registry


def _raw_with_schema_version(
    raw: dict[str, Any],
    schema_version: int,
) -> dict[str, Any]:
    result = dict(raw)
    if schema_version != DEFAULT_SCHEMA_VERSION:
        result["schemaVersion"] = schema_version
    return result


def _provider_only_raw(
    provider_id: str,
    provider_raw: dict[str, Any],
    schema_version: int,
) -> dict[str, Any]:
    return _raw_with_schema_version(
        {"providers": {provider_id: provider_raw}},
        schema_version,
    )


def _build_registry_results_by_provider(
    raw: dict[str, Any],
) -> dict[str, ModelRegistryLoadResult]:
    validate_model_registry_raw(raw)
    schema_version = _schema_version(raw)
    providers_raw = _require_mapping(raw.get("providers"), "providers")
    return {
        provider_id: _build_registry_result(
            _provider_only_raw(provider_id, provider_raw, schema_version)
        )
        for provider_id, provider_raw in providers_raw.items()
    }


def _diagnostics_for_provider_order(
    provider_order: list[str],
    diagnostics_by_provider: dict[str, tuple[ModelRegistryLoadDiagnostic, ...]],
) -> tuple[ModelRegistryLoadDiagnostic, ...]:
    return tuple(
        diagnostic
        for provider_id in provider_order
        for diagnostic in diagnostics_by_provider.get(provider_id, ())
    )


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


def load_builtin_model_registry_with_diagnostics() -> ModelRegistryLoadResult:
    raw = _load_builtin_raw()
    return ModelRegistryLoadResult(registry=_build_registry(raw))


def load_model_registry_from_file(path: str | Path) -> ModelRegistry:
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return _build_registry(_load_json_file(resolved))


def load_model_registry_from_file_with_diagnostics(
    path: str | Path,
) -> ModelRegistryLoadResult:
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return _build_registry_result(_load_json_file(resolved))


def load_model_registry_from_directory(path: str | Path) -> ModelRegistry:
    resolved = Path(path)
    if not resolved.is_dir():
        raise FileNotFoundError(str(resolved))
    providers: dict[str, Provider] = {}
    for child in sorted(resolved.glob("*.json")):
        child_registry = _build_registry(_load_json_file(child))
        providers.update(child_registry.providers)
    return ModelRegistry.from_providers(providers)


def load_model_registry_from_directory_with_diagnostics(
    path: str | Path,
) -> ModelRegistryLoadResult:
    resolved = Path(path)
    if not resolved.is_dir():
        raise FileNotFoundError(str(resolved))
    providers: dict[str, Provider] = {}
    diagnostics_by_provider: dict[str, tuple[ModelRegistryLoadDiagnostic, ...]] = {}
    for child in sorted(resolved.glob("*.json")):
        for provider_id, child_result in _build_registry_results_by_provider(
            _load_json_file(child)
        ).items():
            provider = child_result.registry.providers[provider_id]
            providers[provider_id] = provider
            diagnostics_by_provider[provider_id] = child_result.diagnostics
    diagnostics = _diagnostics_for_provider_order(
        list(providers),
        diagnostics_by_provider,
    )
    return ModelRegistryLoadResult(
        registry=ModelRegistry.from_providers(providers),
        diagnostics=diagnostics,
    )


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
        _validate_typed_schema_version(raw, schema_version)
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
    return load_layered_model_registry_with_diagnostics(
        user_dir=user_dir,
        project_dir=project_dir,
    ).registry


def load_layered_model_registry_with_diagnostics(
    *,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> ModelRegistryLoadResult:
    raw = _load_builtin_raw()
    schema_version = _schema_version(raw)
    external_raw: dict[str, Any] = {}
    user_layer = _load_directory_raw(user_dir) if user_dir is not None else None
    project_layer = (
        _load_directory_raw(project_dir) if project_dir is not None else None
    )
    if user_layer is not None:
        user_raw, user_schema_version = user_layer
        raw = _deep_merge_dict(raw, user_raw)
        external_raw = _deep_merge_dict(external_raw, user_raw)
        schema_version = max(schema_version, user_schema_version)
    if project_layer is not None:
        project_raw, project_schema_version = project_layer
        raw = _deep_merge_dict(raw, project_raw)
        external_raw = _deep_merge_dict(external_raw, project_raw)
        schema_version = max(schema_version, project_schema_version)
    if schema_version != DEFAULT_SCHEMA_VERSION:
        raw["schemaVersion"] = schema_version
    registry = _build_registry(raw)
    diagnostics = _diagnostics_for_provider_order(
        list(registry.providers),
        _legacy_compat_diagnostics_by_provider(external_raw),
    )
    return ModelRegistryLoadResult(registry=registry, diagnostics=diagnostics)


def load_model_registry(
    path: str | Path | None = None,
) -> ModelRegistry:
    return load_model_registry_with_diagnostics(path).registry


def load_model_registry_with_diagnostics(
    path: str | Path | None = None,
) -> ModelRegistryLoadResult:
    if path is None:
        return load_builtin_model_registry_with_diagnostics()

    resolved = Path(path)
    if resolved.is_file():
        return load_model_registry_from_file_with_diagnostics(resolved)
    if resolved.is_dir():
        return load_model_registry_from_directory_with_diagnostics(resolved)
    raise FileNotFoundError(str(resolved))
