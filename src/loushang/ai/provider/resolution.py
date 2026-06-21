from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from loushang.ai.auth.support import resolve_auth_for_model
from loushang.ai.model import Model
from loushang.ai.model.compat_schema import (
    DIALECT_COMPAT_BOOL_MAPPINGS,
    DIALECT_COMPAT_VALUE_MAPPINGS,
    OPENROUTER_ROUTING,
    PROTOCOL_COMPAT_STATUS_MAPPINGS,
    PROVIDER_TRANSPORT,
    REASONING_EFFORT_MAP,
    SUPPORTS_PROMPT_CACHE_KEY,
    UPSTREAM_MODEL_ID,
    VERCEL_GATEWAY_ROUTING,
    resolve_anthropic_messages_compat,
    resolve_openai_completions_compat,
    resolve_openai_responses_compat,
)
from loushang.ai.model.domain import (
    Capabilities,
    Endpoint,
    EndpointProtocolFeatures,
    EndpointRouting,
    EndpointTransport,
    EndpointWireDialect,
)
from loushang.ai.model.registry import (
    ModelRegistry,
    get_default_model_registry,
    has_bound_endpoint_context,
    resolve_model_endpoint,
)

LEGACY_MODEL_CONTRACT_COMPAT_KEYS = frozenset(
    {
        PROVIDER_TRANSPORT,
        OPENROUTER_ROUTING,
        UPSTREAM_MODEL_ID,
        VERCEL_GATEWAY_ROUTING,
    }
)


@dataclass(frozen=True)
class ResolvedEndpoint:
    provider: str
    endpoint: str | None
    api: str
    base_url: str | None = None
    base_url_env: str | None = None
    regions: dict[str, dict] = field(default_factory=dict)
    default_region: str | None = None
    compat: Mapping[str, object] | None = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    transport: EndpointTransport = field(default_factory=EndpointTransport)
    routing: EndpointRouting = field(default_factory=EndpointRouting)
    upstream_model_id: str | None = None
    protocol: EndpointProtocolFeatures = field(default_factory=EndpointProtocolFeatures)
    dialect: EndpointWireDialect = field(default_factory=EndpointWireDialect)
    adapter_compat: Mapping[str, object] | None = field(default_factory=dict)

    def __post_init__(self) -> None:
        compat = dict(self.compat or {})
        adapter_compat = dict(self.adapter_compat or {})
        if compat and adapter_compat and compat != adapter_compat:
            raise TypeError("ResolvedEndpoint accepts either adapter_compat or compat")
        resolved = adapter_compat or compat
        object.__setattr__(self, "compat", resolved)
        object.__setattr__(self, "adapter_compat", resolved)


@dataclass(frozen=True)
class ResolvedRequest:
    provider: str
    endpoint: str | None
    api: str
    base_url: str | None
    region: str | None = None
    candidate_base_urls: tuple[str, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)
    compat: Mapping[str, object] | None = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    transport: EndpointTransport = field(default_factory=EndpointTransport)
    routing: EndpointRouting = field(default_factory=EndpointRouting)
    max_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | int | None = None
    upstream_model_id: str | None = None
    protocol: EndpointProtocolFeatures = field(default_factory=EndpointProtocolFeatures)
    dialect: EndpointWireDialect = field(default_factory=EndpointWireDialect)
    capabilities: Capabilities = field(default_factory=Capabilities)
    adapter_protocol: EndpointProtocolFeatures = field(
        default_factory=EndpointProtocolFeatures
    )
    adapter_dialect: EndpointWireDialect = field(default_factory=EndpointWireDialect)
    adapter_compat: Mapping[str, object] | None = field(default_factory=dict)
    auth_account_id: str | None = None

    def __post_init__(self) -> None:
        compat = dict(self.compat or {})
        adapter_compat = dict(self.adapter_compat or {})
        if compat and adapter_compat and compat != adapter_compat:
            raise TypeError("ResolvedRequest accepts either adapter_compat or compat")
        resolved = adapter_compat or compat
        object.__setattr__(self, "compat", resolved)
        object.__setattr__(self, "adapter_compat", resolved)


def ensure_request_api(provider_api: str, request: ResolvedRequest) -> ResolvedRequest:
    if request.api != provider_api:
        raise ValueError(
            f"Mismatched api: provider={provider_api!r} request.api={request.api!r}"
        )
    return request


def resolve_provider_request(
    provider_api: str,
    model: Model,
    *,
    options=None,
    request: ResolvedRequest | None = None,
) -> ResolvedRequest:
    resolved = (
        request
        if request is not None
        else resolve_request_for_model(model, options=options)
    )
    return ensure_request_api(provider_api, resolved)


def resolve_endpoint_for_model(
    model: Model,
    *,
    catalog=None,
    registry: ModelRegistry | None = None,
) -> ResolvedEndpoint:
    del catalog
    resolved_registry = _registry_for_catalog_lookup(model, registry)
    endpoint = (
        resolved_registry.get_endpoint(model.provider_id, model.endpoint_id)
        if resolved_registry is not None
        else None
    )
    if endpoint is None and has_bound_endpoint_context(model):
        endpoint = resolve_model_endpoint(model)
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
    if endpoint is not None:
        endpoint_model = endpoint.get_model(model.id)
        if endpoint_model is not None:
            request_model = endpoint.bind_model(endpoint_model)
    use_model_overrides = _should_apply_model_request_overrides(
        model,
        endpoint,
        request_model,
    )
    override_model = (
        model if use_model_overrides and request_model is not model else None
    )
    resolved_endpoint = _build_resolved_endpoint(
        request_model,
        endpoint,
        request_model=request_model,
        override_model=override_model,
    )
    base_url = _resolve_base_url(resolved_endpoint, resolved_env)
    raw_compat = dict(resolved_endpoint.adapter_compat or {})
    raw_compat.update(dict(getattr(request_model, "compat", {})))
    defaults = dict(getattr(request_model, "defaults", {}))
    capabilities = getattr(request_model, "capabilities", Capabilities())
    model_contract_compat = _model_compat_overrides(request_model)
    caller_contract_compat = (
        _model_compat_overrides(model) if request_model is not model else {}
    )
    if use_model_overrides:
        raw_compat.update(dict(getattr(model, "compat", {})))
        defaults.update(dict(getattr(model, "defaults", {})))
        capability_overrides = _model_capability_overrides(model)
        if capability_overrides is not None:
            capabilities = capability_overrides
        model_contract_compat.update(_model_compat_overrides(model))
    if caller_contract_compat:
        raw_compat.update(caller_contract_compat)
        model_contract_compat.update(caller_contract_compat)
    if request_model is not model:
        capability_overrides = _model_capability_overrides(model)
        if capability_overrides is not None:
            capabilities = capability_overrides
    raw_compat = _strip_legacy_model_contract_compat(raw_compat)
    _validate_adapter_compat_raw(raw_compat)
    adapter_compat = _resolve_compat_for_api(
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
    auth_account_id = _auth_account_id_from_view(auth_view, headers)
    max_tokens = _resolve_max_tokens(options, defaults)
    reasoning_effort = _resolve_reasoning_effort(options, defaults)
    temperature = _resolve_temperature(options, defaults)
    candidates = []
    if base_url:
        candidates.append(base_url)
    protocol = _resolve_request_protocol(
        resolved_endpoint,
        model_contract_compat,
    )
    dialect = _resolve_request_dialect(
        resolved_endpoint,
        model_contract_compat,
    )
    return ResolvedRequest(
        provider=resolved_endpoint.provider,
        endpoint=resolved_endpoint.endpoint,
        api=resolved_endpoint.api,
        base_url=base_url,
        region=resolved_endpoint.default_region,
        candidate_base_urls=tuple(candidates),
        headers=headers,
        protocol=protocol,
        dialect=dialect,
        capabilities=capabilities,
        adapter_protocol=_merge_protocol_features(
            protocol,
            _protocol_from_compat(adapter_compat),
        ),
        adapter_dialect=_merge_wire_dialect_with_compat(dialect, adapter_compat),
        adapter_compat=adapter_compat,
        defaults=defaults,
        upstream_model_id=resolved_endpoint.upstream_model_id or model.id,
        transport=resolved_endpoint.transport,
        routing=resolved_endpoint.routing,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        auth_account_id=auth_account_id,
    )


def _strip_legacy_model_contract_compat(
    raw: Mapping[str, object],
) -> dict[str, object]:
    return {
        key: value
        for key, value in raw.items()
        if key not in LEGACY_MODEL_CONTRACT_COMPAT_KEYS
    }


def _should_apply_model_request_overrides(
    model: Model,
    endpoint: Endpoint | None,
    request_model: Model,
) -> bool:
    if endpoint is None or endpoint.id == model.endpoint_id:
        return True
    return request_model is not model and not getattr(model, "api", None)


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


def _build_resolved_endpoint(
    model: Model,
    endpoint: Endpoint | None,
    *,
    request_model: Model | None = None,
    override_model: Model | None = None,
) -> ResolvedEndpoint:
    if endpoint is None:
        adapter_compat = _strip_legacy_model_contract_compat(
            getattr(model, "compat", {})
        )
        _validate_adapter_compat_raw(adapter_compat)
        protocol = _protocol_from_compat(adapter_compat)
        dialect = _dialect_from_compat(adapter_compat)
        return ResolvedEndpoint(
            provider=model.provider_id,
            endpoint=model.endpoint_id,
            api=getattr(model, "api", None) or model.endpoint_id,
            base_url=getattr(model, "base_url", None),
            base_url_env=getattr(model, "base_url_env", None),
            default_region=getattr(model, "region", None),
            protocol=protocol,
            dialect=dialect,
            adapter_compat=adapter_compat,
            defaults=dict(getattr(model, "defaults", {})),
            upstream_model_id=_model_upstream_id(model),
            transport=_model_transport(model),
            routing=_model_routing(model),
        )
    endpoint_compat = endpoint.compat.merged(endpoint.protocol.to_compat()).merged(
        endpoint.dialect.to_compat()
    )
    transport_raw = endpoint.transport.to_raw()
    if request_model is not None:
        transport_raw = _deep_merge_raw_mapping(
            transport_raw,
            _model_transport_raw(request_model, own_only=True),
        )
    if override_model is not None:
        transport_raw = _deep_merge_raw_mapping(
            transport_raw,
            _model_transport_raw(override_model, own_only=True),
        )
    routing_raw = endpoint.routing.to_raw()
    if request_model is not None:
        routing_raw = _deep_merge_raw_mapping(
            routing_raw,
            _model_routing_raw(request_model, own_only=True),
        )
    if override_model is not None:
        routing_raw = _deep_merge_raw_mapping(
            routing_raw,
            _model_routing_raw(override_model, own_only=True),
        )
    upstream_model_id = _model_upstream_id(request_model or model)
    if override_model is not None:
        upstream_model_id = _model_upstream_id(override_model) or upstream_model_id
    transport = EndpointTransport.from_raw(transport_raw)
    routing = EndpointRouting.from_raw(routing_raw)
    adapter_compat = _strip_legacy_model_contract_compat(endpoint_compat)
    _validate_adapter_compat_raw(adapter_compat)
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
        protocol=_merge_protocol_features(
            _protocol_from_compat(adapter_compat),
            endpoint.protocol,
        ),
        dialect=_merge_wire_dialect(
            _dialect_from_compat(adapter_compat),
            endpoint.dialect,
        ),
        adapter_compat=adapter_compat,
        defaults=dict(endpoint.defaults),
        upstream_model_id=upstream_model_id,
        transport=transport,
        routing=routing,
    )


def _resolve_request_protocol(
    endpoint: ResolvedEndpoint,
    model_compat: Mapping[str, object],
) -> EndpointProtocolFeatures:
    return _merge_protocol_features(
        endpoint.protocol,
        _protocol_from_compat(model_compat),
    )


def _resolve_request_dialect(
    endpoint: ResolvedEndpoint,
    model_compat: Mapping[str, object],
) -> EndpointWireDialect:
    return _merge_wire_dialect_with_compat(endpoint.dialect, model_compat)


def _merge_protocol_features(
    base: EndpointProtocolFeatures,
    override: EndpointProtocolFeatures,
) -> EndpointProtocolFeatures:
    return EndpointProtocolFeatures.from_raw(
        _deep_merge_raw_mapping(base.to_raw(), override.to_raw())
    )


def _merge_wire_dialect(
    base: EndpointWireDialect,
    override: EndpointWireDialect,
) -> EndpointWireDialect:
    return EndpointWireDialect.from_raw(
        _deep_merge_raw_mapping(base.to_raw(), override.to_raw())
    )


def _merge_wire_dialect_with_compat(
    base: EndpointWireDialect,
    compat: Mapping[str, object],
) -> EndpointWireDialect:
    return _clear_wire_dialect_from_compat(
        _merge_wire_dialect(base, _dialect_from_compat(compat)),
        compat,
    )


def _clear_wire_dialect_from_compat(
    dialect: EndpointWireDialect,
    compat: Mapping[str, object],
) -> EndpointWireDialect:
    raw = dialect.to_raw()
    changed = False
    for compat_key, section, dialect_key in DIALECT_COMPAT_VALUE_MAPPINGS:
        if compat_key not in compat or compat[compat_key] is not None:
            continue
        if section is None:
            if dialect_key in raw:
                raw.pop(dialect_key, None)
                changed = True
            continue
        section_raw = raw.get(section)
        if not isinstance(section_raw, dict) or dialect_key not in section_raw:
            continue
        section_copy = dict(section_raw)
        section_copy.pop(dialect_key, None)
        if section_copy:
            raw[section] = section_copy
        else:
            raw.pop(section, None)
        changed = True
    if not changed:
        return dialect
    return EndpointWireDialect.from_raw(raw)


def _model_compat_overrides(model: Model) -> dict[str, object]:
    compat = getattr(model, "contract_compat", None)
    if isinstance(compat, Mapping):
        return _strip_legacy_model_contract_compat(compat)
    return _strip_legacy_model_contract_compat(getattr(model, "compat", {}))


def _model_capability_overrides(model: Model) -> Capabilities | None:
    capabilities = getattr(model, "contract_capabilities", None)
    if isinstance(capabilities, Capabilities):
        return capabilities
    fallback = getattr(model, "capabilities", Capabilities())
    return fallback if fallback != Capabilities() else None


def _validate_adapter_compat_raw(raw: Mapping[str, object]) -> None:
    bool_keys = {compat_key for compat_key, _, _ in PROTOCOL_COMPAT_STATUS_MAPPINGS} | {
        compat_key for compat_key, _, _ in DIALECT_COMPAT_BOOL_MAPPINGS
    }
    bool_keys.add(SUPPORTS_PROMPT_CACHE_KEY)
    for key in sorted(bool_keys):
        if key in raw and not isinstance(raw[key], bool):
            raise ValueError(f"compat key {key} must be boolean")
    for key in sorted(compat_key for compat_key, _, _ in DIALECT_COMPAT_VALUE_MAPPINGS):
        if key not in raw:
            continue
        value = raw[key]
        if key in {"thinkingFormat", "cacheControlFormat"} and value is None:
            continue
        if not isinstance(value, str) or not value:
            raise ValueError(f"compat key {key} must be non-empty string")
    if REASONING_EFFORT_MAP in raw and not _is_string_or_none_mapping(
        raw[REASONING_EFFORT_MAP]
    ):
        raise ValueError(f"compat key {REASONING_EFFORT_MAP} must be string map")


def _is_string_or_none_mapping(value: object) -> bool:
    return isinstance(value, Mapping) and all(
        isinstance(item_key, str)
        and (item_value is None or isinstance(item_value, str))
        for item_key, item_value in value.items()
    )


def _protocol_from_compat(
    compat: Mapping[str, object],
) -> EndpointProtocolFeatures:
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
    return EndpointProtocolFeatures.from_raw(raw)


def _dialect_from_compat(
    compat: Mapping[str, object],
) -> EndpointWireDialect:
    raw: dict[str, object] = {}
    for compat_key, section, dialect_key in DIALECT_COMPAT_BOOL_MAPPINGS:
        if compat_key in compat:
            _set_dialect_bool(raw, section, dialect_key, compat[compat_key])
    for compat_key, value_section, dialect_key in DIALECT_COMPAT_VALUE_MAPPINGS:
        if compat_key in compat:
            _set_dialect_value(raw, value_section, dialect_key, compat[compat_key])
    return EndpointWireDialect.from_raw(raw)


def _set_protocol_status(
    raw: dict[str, object],
    section: str | None,
    key: str,
    value: object,
) -> None:
    if not isinstance(value, bool):
        return
    status = "supported" if value else "unsupported"
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
    if not isinstance(value, Mapping):
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


def _model_transport(model: Model) -> EndpointTransport:
    return EndpointTransport.from_raw(_model_transport_raw(model, own_only=False))


def _model_routing(model: Model) -> EndpointRouting:
    return EndpointRouting.from_raw(_model_routing_raw(model, own_only=False))


def _model_upstream_id(model: Model) -> str | None:
    value = getattr(model, "upstream_id", None)
    if isinstance(value, str) and value.strip():
        return value
    compat = getattr(model, "compat", {})
    legacy_value = (
        compat.get(UPSTREAM_MODEL_ID) if isinstance(compat, Mapping) else None
    )
    return (
        legacy_value if isinstance(legacy_value, str) and legacy_value.strip() else None
    )


def _model_transport_raw(model: Model, *, own_only: bool) -> dict[str, object]:
    raw = _deep_merge_raw_mapping(
        _transport_raw_from_legacy_compat(
            getattr(model, "_transport_legacy_raw", None)
        ),
        _transport_raw_from_legacy_compat(getattr(model, "compat", {})),
    )
    own_raw = getattr(model, "_transport_own_raw", None)
    if own_only and isinstance(own_raw, Mapping):
        transport_raw = dict(own_raw)
    elif own_only:
        transport_raw = {}
    else:
        transport = getattr(model, "transport", None)
        transport_raw = (
            transport.to_raw() if isinstance(transport, EndpointTransport) else {}
        )
    return _deep_merge_raw_mapping(raw, transport_raw)


def _model_routing_raw(model: Model, *, own_only: bool) -> dict[str, object]:
    raw = _deep_merge_raw_mapping(
        _routing_raw_from_legacy_compat(getattr(model, "_routing_legacy_raw", None)),
        _routing_raw_from_legacy_compat(getattr(model, "compat", {})),
    )
    own_raw = getattr(model, "_routing_own_raw", None)
    if own_only and isinstance(own_raw, Mapping):
        routing_raw = dict(own_raw)
    elif own_only:
        routing_raw = {}
    else:
        routing = getattr(model, "routing", None)
        routing_raw = routing.to_raw() if isinstance(routing, EndpointRouting) else {}
    return _deep_merge_raw_mapping(raw, routing_raw)


def _transport_raw_from_legacy_compat(
    compat: Mapping[str, object] | None,
) -> dict[str, object]:
    if compat is None:
        return {}
    value = compat.get(PROVIDER_TRANSPORT)
    if not isinstance(value, str) or not value:
        return {}
    return {"kind": value}


def _routing_raw_from_legacy_compat(
    compat: Mapping[str, object] | None,
) -> dict[str, object]:
    if compat is None:
        return {}
    request_overrides: dict[str, object] = {}
    for compat_key, routing_key in (
        (OPENROUTER_ROUTING, "openrouter"),
        (VERCEL_GATEWAY_ROUTING, "vercelGateway"),
    ):
        value = compat.get(compat_key)
        if isinstance(value, Mapping) and value:
            request_overrides[routing_key] = dict(value)
    if not request_overrides:
        return {}
    return {"requestOverrides": request_overrides}


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
    endpoint: ResolvedEndpoint,
    env: dict[str, str] | None,
) -> str | None:
    resolved_env = env or {}
    if endpoint.base_url_env:
        value = resolved_env.get(endpoint.base_url_env)
        if isinstance(value, str) and value:
            return value
    if endpoint.base_url is None:
        return None
    return _expand_env_template(endpoint.base_url, resolved_env)


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
