from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import InitVar, dataclass, field, replace
from enum import Enum
from math import isfinite
from typing import Literal, cast

from loushang.ai.model.compat_schema import (
    DIALECT_COMPAT_BOOL_MAPPINGS,
    DIALECT_COMPAT_VALUE_MAPPINGS,
    PROTOCOL_COMPAT_STATUS_MAPPINGS,
    REASONING_EFFORT_MAP,
    UPSTREAM_MODEL_ID,
)

Modality = Literal["text", "image", "video", "audio", "vector"]
ALLOWED_MODALITIES: tuple[Modality, ...] = ("text", "image", "video", "audio", "vector")


class SupportStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"

    @classmethod
    def from_raw(cls, raw: object) -> "SupportStatus":
        if isinstance(raw, SupportStatus):
            return raw
        if isinstance(raw, str):
            try:
                return cls(raw)
            except ValueError as error:
                raise ValueError(f"unsupported support status: {raw!r}") from error
        raise ValueError(f"support status must be a string: {raw!r}")


def _status_from_raw(raw: Mapping[str, object], key: str) -> SupportStatus:
    if key not in raw:
        return SupportStatus.UNKNOWN
    return SupportStatus.from_raw(raw[key])


def _status_to_raw(status: SupportStatus, *, explicit: bool = False) -> str | None:
    if status is SupportStatus.UNKNOWN and not explicit:
        return None
    return status.value


def _explicit_keys(raw: Mapping[str, object], keys: tuple[str, ...]) -> frozenset[str]:
    return frozenset(key for key in keys if key in raw)


def _protocol_status_to_compat_bool(value: object) -> bool:
    return SupportStatus.from_raw(value) is SupportStatus.SUPPORTED


def _normalize_status_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        object.__setattr__(
            instance,
            attr,
            SupportStatus.from_raw(getattr(instance, attr)),
        )


def _normalize_optional_bool_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"wire dialect field must be a boolean: {attr}")


def _normalize_optional_str_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"wire dialect field must be a non-empty string: {attr}")


def _normalize_optional_transport_str_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"transport field must be a non-empty string: {attr}")


def _normalize_optional_transport_bool_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"transport field must be a boolean: {attr}")


def _normalize_optional_transport_number_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"transport field must be a positive number: {attr}")


def _optional_bool_from_raw(raw: Mapping[str, object], key: str) -> bool | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, bool):
        return value
    raise ValueError(f"wire dialect field must be a boolean: {key}")


def _optional_str_from_raw(raw: Mapping[str, object], key: str) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"wire dialect field must be a non-empty string: {key}")


def _optional_transport_str_from_raw(
    raw: Mapping[str, object],
    key: str,
) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"transport field must be a non-empty string: {key}")


def _optional_transport_bool_from_raw(
    raw: Mapping[str, object],
    key: str,
) -> bool | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, bool):
        return value
    raise ValueError(f"transport field must be a boolean: {key}")


def _optional_transport_number_from_raw(
    raw: Mapping[str, object],
    key: str,
) -> float | int | None:
    if key not in raw:
        return None
    value = raw[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"transport field must be a positive number: {key}")
    return value


def _optional_dialect_section_from_raw(
    raw: Mapping[str, object],
    key: str,
) -> Mapping[str, object] | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, Mapping):
        return value
    raise ValueError(f"wire dialect section must be an object: {key}")


def _copy_raw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _copy_raw_value(entry) for key, entry in value.items()}
    if isinstance(value, list):
        return [_copy_raw_value(entry) for entry in value]
    return value


def _copy_raw_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _copy_raw_value(entry) for key, entry in value.items()}


def _deep_merge_raw_mapping(
    base: Mapping[str, object],
    override: Mapping[str, object],
) -> dict[str, object]:
    result = _copy_raw_mapping(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge_raw_mapping(existing, value)
            continue
        result[key] = _copy_raw_value(value)
    return result


def _routing_request_overrides_from_raw(
    raw: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    if "requestOverrides" not in raw:
        return {}
    value = raw["requestOverrides"]
    if not isinstance(value, Mapping):
        raise ValueError("routing field must be an object: requestOverrides")
    overrides: dict[str, dict[str, object]] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("routing requestOverrides keys must be non-empty strings")
        if not isinstance(entry, Mapping):
            raise ValueError(
                "routing requestOverrides entries must be objects: "
                f"requestOverrides.{key}"
            )
        overrides[key] = _copy_raw_mapping(entry)
    return overrides


def _legacy_transport_routing_compat_raw(
    transport_raw: Mapping[str, object] | None,
    routing_raw: Mapping[str, object] | None,
) -> dict[str, object]:
    raw: dict[str, object] = {}
    if transport_raw is not None:
        raw.update(_copy_raw_mapping(transport_raw))
    if routing_raw is not None:
        raw.update(_copy_raw_mapping(routing_raw))
    return raw


@dataclass(frozen=True)
class EndpointProtocolRoles:
    developer: SupportStatus = SupportStatus.UNKNOWN
    _explicit_keys: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        _normalize_status_attrs(self, "developer")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointProtocolRoles":
        raw = raw or {}
        return cls(
            developer=_status_from_raw(raw, "developer"),
            _explicit_keys=_explicit_keys(raw, ("developer",)),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if value := _status_to_raw(
            self.developer,
            explicit="developer" in self._explicit_keys,
        ):
            raw["developer"] = value
        return raw


@dataclass(frozen=True)
class EndpointProtocolStreaming:
    usage: SupportStatus = SupportStatus.UNKNOWN
    reasoning_delta: SupportStatus = SupportStatus.UNKNOWN
    _explicit_keys: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        _normalize_status_attrs(self, "usage", "reasoning_delta")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointProtocolStreaming":
        raw = raw or {}
        return cls(
            usage=_status_from_raw(raw, "usage"),
            reasoning_delta=_status_from_raw(raw, "reasoningDelta"),
            _explicit_keys=_explicit_keys(raw, ("usage", "reasoningDelta")),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if value := _status_to_raw(
            self.usage,
            explicit="usage" in self._explicit_keys,
        ):
            raw["usage"] = value
        if value := _status_to_raw(
            self.reasoning_delta,
            explicit="reasoningDelta" in self._explicit_keys,
        ):
            raw["reasoningDelta"] = value
        return raw


@dataclass(frozen=True)
class EndpointProtocolReasoning:
    effort: SupportStatus = SupportStatus.UNKNOWN
    effort_map: dict[str, str | None] = field(default_factory=dict)
    interleaved: SupportStatus = SupportStatus.UNKNOWN
    _explicit_keys: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        _normalize_status_attrs(self, "effort", "interleaved")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointProtocolReasoning":
        raw = raw or {}
        return cls(
            effort=_status_from_raw(raw, "effort"),
            effort_map=_as_optional_str_dict(raw.get("effortMap")),
            interleaved=_status_from_raw(raw, "interleaved"),
            _explicit_keys=_explicit_keys(raw, ("effort", "effortMap", "interleaved")),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if value := _status_to_raw(
            self.effort,
            explicit="effort" in self._explicit_keys,
        ):
            raw["effort"] = value
        if self.effort_map or "effortMap" in self._explicit_keys:
            raw["effortMap"] = dict(self.effort_map)
        if value := _status_to_raw(
            self.interleaved,
            explicit="interleaved" in self._explicit_keys,
        ):
            raw["interleaved"] = value
        return raw


@dataclass(frozen=True)
class EndpointProtocolTools:
    strict_schema: SupportStatus = SupportStatus.UNKNOWN
    eager_input_stream: SupportStatus = SupportStatus.UNKNOWN
    fine_grained: SupportStatus = SupportStatus.UNKNOWN
    _explicit_keys: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        _normalize_status_attrs(
            self,
            "strict_schema",
            "eager_input_stream",
            "fine_grained",
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointProtocolTools":
        raw = raw or {}
        return cls(
            strict_schema=_status_from_raw(raw, "strictSchema"),
            eager_input_stream=_status_from_raw(raw, "eagerInputStream"),
            fine_grained=_status_from_raw(raw, "fineGrained"),
            _explicit_keys=_explicit_keys(
                raw,
                ("strictSchema", "eagerInputStream", "fineGrained"),
            ),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if value := _status_to_raw(
            self.strict_schema,
            explicit="strictSchema" in self._explicit_keys,
        ):
            raw["strictSchema"] = value
        if value := _status_to_raw(
            self.eager_input_stream,
            explicit="eagerInputStream" in self._explicit_keys,
        ):
            raw["eagerInputStream"] = value
        if value := _status_to_raw(
            self.fine_grained,
            explicit="fineGrained" in self._explicit_keys,
        ):
            raw["fineGrained"] = value
        return raw


@dataclass(frozen=True)
class EndpointProtocolCache:
    on_tools: SupportStatus = SupportStatus.UNKNOWN
    long_retention: SupportStatus = SupportStatus.UNKNOWN
    _explicit_keys: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        _normalize_status_attrs(self, "on_tools", "long_retention")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointProtocolCache":
        raw = raw or {}
        return cls(
            on_tools=_status_from_raw(raw, "onTools"),
            long_retention=_status_from_raw(raw, "longRetention"),
            _explicit_keys=_explicit_keys(raw, ("onTools", "longRetention")),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if value := _status_to_raw(
            self.on_tools,
            explicit="onTools" in self._explicit_keys,
        ):
            raw["onTools"] = value
        if value := _status_to_raw(
            self.long_retention,
            explicit="longRetention" in self._explicit_keys,
        ):
            raw["longRetention"] = value
        return raw


@dataclass(frozen=True)
class EndpointProtocolSession:
    id_header: SupportStatus = SupportStatus.UNKNOWN
    affinity_headers: SupportStatus = SupportStatus.UNKNOWN
    _explicit_keys: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        _normalize_status_attrs(self, "id_header", "affinity_headers")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointProtocolSession":
        raw = raw or {}
        return cls(
            id_header=_status_from_raw(raw, "idHeader"),
            affinity_headers=_status_from_raw(raw, "affinityHeaders"),
            _explicit_keys=_explicit_keys(raw, ("idHeader", "affinityHeaders")),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if value := _status_to_raw(
            self.id_header,
            explicit="idHeader" in self._explicit_keys,
        ):
            raw["idHeader"] = value
        if value := _status_to_raw(
            self.affinity_headers,
            explicit="affinityHeaders" in self._explicit_keys,
        ):
            raw["affinityHeaders"] = value
        return raw


@dataclass(frozen=True)
class EndpointProtocolFeatures:
    store: SupportStatus = SupportStatus.UNKNOWN
    roles: EndpointProtocolRoles = field(default_factory=EndpointProtocolRoles)
    streaming: EndpointProtocolStreaming = field(
        default_factory=EndpointProtocolStreaming
    )
    reasoning: EndpointProtocolReasoning = field(
        default_factory=EndpointProtocolReasoning
    )
    tools: EndpointProtocolTools = field(default_factory=EndpointProtocolTools)
    cache: EndpointProtocolCache = field(default_factory=EndpointProtocolCache)
    session: EndpointProtocolSession = field(default_factory=EndpointProtocolSession)
    _explicit_keys: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        _normalize_status_attrs(self, "store")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointProtocolFeatures":
        raw = raw or {}
        return cls(
            store=_status_from_raw(raw, "store"),
            roles=EndpointProtocolRoles.from_raw(_mapping_or_none(raw.get("roles"))),
            streaming=EndpointProtocolStreaming.from_raw(
                _mapping_or_none(raw.get("streaming"))
            ),
            reasoning=EndpointProtocolReasoning.from_raw(
                _mapping_or_none(raw.get("reasoning"))
            ),
            tools=EndpointProtocolTools.from_raw(_mapping_or_none(raw.get("tools"))),
            cache=EndpointProtocolCache.from_raw(_mapping_or_none(raw.get("cache"))),
            session=EndpointProtocolSession.from_raw(
                _mapping_or_none(raw.get("session"))
            ),
            _explicit_keys=_explicit_keys(raw, ("store",)),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if store_value := _status_to_raw(
            self.store,
            explicit="store" in self._explicit_keys,
        ):
            raw["store"] = store_value
        for key, section_raw in (
            ("roles", self.roles.to_raw()),
            ("streaming", self.streaming.to_raw()),
            ("reasoning", self.reasoning.to_raw()),
            ("tools", self.tools.to_raw()),
            ("cache", self.cache.to_raw()),
            ("session", self.session.to_raw()),
        ):
            if section_raw:
                raw[key] = section_raw
        return raw

    def to_compat(self) -> dict[str, object]:
        raw = self.to_raw()
        compat: dict[str, object] = {}
        for compat_key, section, protocol_key in PROTOCOL_COMPAT_STATUS_MAPPINGS:
            if section is None:
                if protocol_key not in raw:
                    continue
                value = raw[protocol_key]
            else:
                section_raw = raw.get(section)
                if not isinstance(section_raw, dict) or protocol_key not in section_raw:
                    continue
                value = section_raw[protocol_key]
            # The legacy compat bridge has no third state, so explicit
            # "unknown" projects conservatively to False.
            compat[compat_key] = _protocol_status_to_compat_bool(value)
        reasoning_raw = raw.get("reasoning")
        if isinstance(reasoning_raw, dict) and "effortMap" in reasoning_raw:
            compat[REASONING_EFFORT_MAP] = dict(reasoning_raw["effortMap"])
        return compat


@dataclass(frozen=True)
class EndpointDialectTools:
    result_name_required: bool | None = None
    assistant_bridge_required: bool | None = None
    stream_flag: bool | None = None

    def __post_init__(self) -> None:
        _normalize_optional_bool_attrs(
            self,
            "result_name_required",
            "assistant_bridge_required",
            "stream_flag",
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointDialectTools":
        raw = raw or {}
        return cls(
            result_name_required=_optional_bool_from_raw(raw, "resultNameRequired"),
            assistant_bridge_required=_optional_bool_from_raw(
                raw,
                "assistantBridgeRequired",
            ),
            stream_flag=_optional_bool_from_raw(raw, "streamFlag"),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if self.result_name_required is not None:
            raw["resultNameRequired"] = self.result_name_required
        if self.assistant_bridge_required is not None:
            raw["assistantBridgeRequired"] = self.assistant_bridge_required
        if self.stream_flag is not None:
            raw["streamFlag"] = self.stream_flag
        return raw


@dataclass(frozen=True)
class EndpointDialectReasoning:
    wire_format: str | None = None
    thinking_as_text: bool | None = None
    assistant_content_required: bool | None = None

    def __post_init__(self) -> None:
        _normalize_optional_str_attrs(self, "wire_format")
        _normalize_optional_bool_attrs(
            self,
            "thinking_as_text",
            "assistant_content_required",
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointDialectReasoning":
        raw = raw or {}
        return cls(
            wire_format=_optional_str_from_raw(raw, "wireFormat"),
            thinking_as_text=_optional_bool_from_raw(raw, "thinkingAsText"),
            assistant_content_required=_optional_bool_from_raw(
                raw,
                "assistantContentRequired",
            ),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if self.wire_format is not None:
            raw["wireFormat"] = self.wire_format
        if self.thinking_as_text is not None:
            raw["thinkingAsText"] = self.thinking_as_text
        if self.assistant_content_required is not None:
            raw["assistantContentRequired"] = self.assistant_content_required
        return raw


@dataclass(frozen=True)
class EndpointDialectCache:
    control_format: str | None = None

    def __post_init__(self) -> None:
        _normalize_optional_str_attrs(self, "control_format")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointDialectCache":
        raw = raw or {}
        return cls(control_format=_optional_str_from_raw(raw, "controlFormat"))

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if self.control_format is not None:
            raw["controlFormat"] = self.control_format
        return raw


@dataclass(frozen=True)
class EndpointWireDialect:
    max_output_tokens_field: str | None = None
    tools: EndpointDialectTools = field(default_factory=EndpointDialectTools)
    reasoning: EndpointDialectReasoning = field(
        default_factory=EndpointDialectReasoning
    )
    cache: EndpointDialectCache = field(default_factory=EndpointDialectCache)

    def __post_init__(self) -> None:
        _normalize_optional_str_attrs(self, "max_output_tokens_field")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointWireDialect":
        raw = raw or {}
        return cls(
            max_output_tokens_field=_optional_str_from_raw(
                raw,
                "maxOutputTokensField",
            ),
            tools=EndpointDialectTools.from_raw(
                _optional_dialect_section_from_raw(raw, "tools")
            ),
            reasoning=EndpointDialectReasoning.from_raw(
                _optional_dialect_section_from_raw(raw, "reasoning")
            ),
            cache=EndpointDialectCache.from_raw(
                _optional_dialect_section_from_raw(raw, "cache")
            ),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if self.max_output_tokens_field is not None:
            raw["maxOutputTokensField"] = self.max_output_tokens_field
        for key, section_raw in (
            ("tools", self.tools.to_raw()),
            ("reasoning", self.reasoning.to_raw()),
            ("cache", self.cache.to_raw()),
        ):
            if section_raw:
                raw[key] = section_raw
        return raw

    def to_compat(self) -> dict[str, object]:
        raw = self.to_raw()
        compat: dict[str, object] = {}
        for compat_key, section, dialect_key in DIALECT_COMPAT_BOOL_MAPPINGS:
            section_raw = raw.get(section)
            if isinstance(section_raw, dict) and dialect_key in section_raw:
                compat[compat_key] = section_raw[dialect_key]
        for compat_key, value_section, dialect_key in DIALECT_COMPAT_VALUE_MAPPINGS:
            if value_section is None:
                if dialect_key in raw:
                    compat[compat_key] = raw[dialect_key]
                continue
            section_raw = raw.get(value_section)
            if isinstance(section_raw, dict) and dialect_key in section_raw:
                compat[compat_key] = section_raw[dialect_key]
        return compat


@dataclass(frozen=True)
class EndpointTransport:
    kind: str | None = None
    stream: str | None = None
    fallback: bool | None = None
    timeout: float | int | None = None

    def __post_init__(self) -> None:
        _normalize_optional_transport_str_attrs(self, "kind", "stream")
        _normalize_optional_transport_bool_attrs(self, "fallback")
        _normalize_optional_transport_number_attrs(self, "timeout")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointTransport":
        raw = raw or {}
        return cls(
            kind=_optional_transport_str_from_raw(raw, "kind"),
            stream=_optional_transport_str_from_raw(raw, "stream"),
            fallback=_optional_transport_bool_from_raw(raw, "fallback"),
            timeout=_optional_transport_number_from_raw(raw, "timeout"),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if self.kind is not None:
            raw["kind"] = self.kind
        if self.stream is not None:
            raw["stream"] = self.stream
        if self.fallback is not None:
            raw["fallback"] = self.fallback
        if self.timeout is not None:
            raw["timeout"] = self.timeout
        return raw


@dataclass(frozen=True)
class EndpointRouting:
    request_overrides: dict[str, dict[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key, value in self.request_overrides.items():
            if not isinstance(key, str) or not key:
                raise ValueError(
                    "routing requestOverrides keys must be non-empty strings"
                )
            if not isinstance(value, Mapping):
                raise ValueError(
                    "routing requestOverrides entries must be objects: "
                    f"requestOverrides.{key}"
                )
        object.__setattr__(
            self,
            "request_overrides",
            {
                key: _copy_raw_mapping(value)
                for key, value in self.request_overrides.items()
            },
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointRouting":
        raw = raw or {}
        return cls(request_overrides=_routing_request_overrides_from_raw(raw))

    def to_raw(self) -> dict[str, object]:
        if not self.request_overrides:
            return {}
        return {
            "requestOverrides": {
                key: _copy_raw_mapping(value)
                for key, value in self.request_overrides.items()
            }
        }


@dataclass(frozen=True)
class Auth:
    kind: str = "apiKey"
    api_key_env: str | None = None
    api_key_envs: tuple[str, ...] = ()
    header: str = "Authorization"
    prefix: str = "Bearer "
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Auth | None":
        if not raw:
            return None
        return cls(
            kind=str(raw.get("kind", "apiKey")),
            api_key_env=_as_optional_str(raw.get("apiKeyEnv")),
            api_key_envs=_as_str_tuple(raw.get("apiKeyEnvs")),
            header=str(raw.get("header", "Authorization")),
            prefix=str(raw.get("prefix", "Bearer ")),
            extra_headers=_as_str_dict(raw.get("extraHeaders")),
        )

    def to_raw(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "apiKeyEnv": self.api_key_env,
            "apiKeyEnvs": list(self.api_key_envs),
            "header": self.header,
            "prefix": self.prefix,
            "extraHeaders": dict(self.extra_headers),
        }


@dataclass(frozen=True)
class Pricing:
    currency: str | None = None
    input: float | int | None = None
    output: float | int | None = None
    cache_read: float | int | None = None
    cache_write: float | int | None = None

    def __post_init__(self) -> None:
        for attr in ("input", "output", "cache_read", "cache_write"):
            value = getattr(self, attr)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"pricing field must be a non-negative number: {attr}")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Pricing | None":
        if raw is None:
            return None
        return cls(
            currency=_as_optional_str(raw.get("currency")),
            input=_as_optional_number(raw.get("input")),
            output=_as_optional_number(raw.get("output")),
            cache_read=_as_optional_number(raw.get("cacheRead")),
            cache_write=_as_optional_number(raw.get("cacheWrite")),
        )

    def to_raw(self) -> dict[str, object]:
        raw = {
            "currency": self.currency,
            "input": self.input,
            "output": self.output,
            "cacheRead": self.cache_read,
            "cacheWrite": self.cache_write,
        }
        return {key: value for key, value in raw.items() if value is not None}


@dataclass(frozen=True)
class Capabilities:
    input: tuple[Modality, ...] = ("text",)
    output: tuple[Modality, ...] = ("text",)
    context_window: int | None = None
    max_tokens: int | None = None
    reasoning: bool = False
    stream: bool = False
    tool_use: bool = False
    structured_output: bool = False
    attachment: bool = False
    temperature: bool = False

    @property
    def supports_thinking(self) -> bool:
        return self.reasoning

    @property
    def supports_image_input(self) -> bool:
        return "image" in self.input

    @property
    def supports_image_output(self) -> bool:
        return "image" in self.output

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Capabilities":
        raw = raw or {}
        capabilities_raw = raw.get("capabilities")
        if isinstance(capabilities_raw, Mapping):
            raw = capabilities_raw
        return cls(
            input=_parse_modalities(raw.get("input")),
            output=_parse_modalities(raw.get("output")),
            context_window=_as_optional_int(raw.get("contextWindow")),
            max_tokens=_as_optional_int(raw.get("maxTokens")),
            reasoning=bool(raw.get("reasoning", False)),
            stream=bool(raw.get("stream", False)),
            tool_use=bool(raw.get("toolUse", False)),
            structured_output=bool(raw.get("structuredOutput", False)),
            attachment=bool(raw.get("attachment", False)),
            temperature=bool(raw.get("temperature", False)),
        )

    def to_raw(self) -> dict[str, object]:
        return {
            "capabilities": {
                "contextWindow": self.context_window,
                "maxTokens": self.max_tokens,
                "input": list(self.input),
                "output": list(self.output),
                "reasoning": self.reasoning,
                "stream": self.stream,
                "toolUse": self.tool_use,
                "structuredOutput": self.structured_output,
                "attachment": self.attachment,
                "temperature": self.temperature,
            }
        }


@dataclass(frozen=True, init=False)
class Compat(Mapping[str, object]):
    items_by_key: dict[str, object] = field(default_factory=dict)

    def __init__(
        self,
        *,
        items_by_key: Mapping[str, object] | None = None,
        values: Mapping[str, object] | None = None,
    ) -> None:
        if items_by_key is not None and values is not None:
            raise TypeError("Compat accepts either items_by_key or values, not both.")
        source = items_by_key if items_by_key is not None else values
        object.__setattr__(self, "items_by_key", dict(source or {}))

    def __getitem__(self, key: str) -> object:
        return self.items_by_key[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.items_by_key)

    def __len__(self) -> int:
        return len(self.items_by_key)

    def get(self, key: str, default: object | None = None) -> object | None:
        return self.items_by_key.get(key, default)

    def merged(self, other: Mapping[str, object] | None = None) -> "Compat":
        merged = dict(self.items_by_key)
        if other is not None:
            merged.update(dict(other))
        return Compat(items_by_key=merged)

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Compat":
        return cls(items_by_key=dict(raw or {}))

    def to_raw(self) -> dict[str, object]:
        return dict(self.items_by_key)


@dataclass(frozen=True)
class Defaults(Mapping[str, object]):
    items_by_key: dict[str, object] = field(default_factory=dict)

    def __getitem__(self, key: str) -> object:
        return self.items_by_key[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.items_by_key)

    def __len__(self) -> int:
        return len(self.items_by_key)

    def get(self, key: str, default: object | None = None) -> object | None:
        return self.items_by_key.get(key, default)

    def merged(self, other: Mapping[str, object] | None = None) -> "Defaults":
        merged = dict(self.items_by_key)
        if other is not None:
            merged.update(dict(other))
        return Defaults(items_by_key=merged)

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Defaults":
        return cls(items_by_key=dict(raw or {}))

    def to_raw(self) -> dict[str, object]:
        return dict(self.items_by_key)


@dataclass(frozen=True)
class Model:
    id: str
    _endpoint_key: str = ""
    provider: InitVar[str | None] = None
    endpoint: InitVar[str | None] = None
    api: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    region: str | None = None
    lane: str | None = None
    preferred_endpoint: bool = False
    auth: Auth | None = None
    _auth_inherited: bool = False
    name: str | None = None
    family: str | None = None
    alias: str | None = None
    knowledge: str | None = None
    release_date: str | None = None
    last_updated: str | None = None
    capabilities: Capabilities = field(default_factory=Capabilities)
    pricing: Pricing | None = None
    compat: Compat = field(default_factory=Compat)
    defaults: Defaults = field(default_factory=Defaults)
    transport: EndpointTransport = field(default_factory=EndpointTransport)
    _transport_own_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    _transport_legacy_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    routing: EndpointRouting = field(default_factory=EndpointRouting)
    _routing_own_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    _routing_legacy_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    upstream_id: str | None = None
    _upstream_id_legacy_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    def __post_init__(self, provider: str | None, endpoint: str | None) -> None:
        if self.upstream_id is not None and (
            not isinstance(self.upstream_id, str) or not self.upstream_id.strip()
        ):
            raise ValueError("model upstream_id must be a non-empty string")
        if self._transport_own_raw is None and self._transport_legacy_raw is None:
            object.__setattr__(self, "_transport_own_raw", self.transport.to_raw())
        if self._routing_own_raw is None and self._routing_legacy_raw is None:
            object.__setattr__(self, "_routing_own_raw", self.routing.to_raw())
        if not self._endpoint_key and provider is not None and endpoint is not None:
            object.__setattr__(
                self,
                "_endpoint_key",
                build_endpoint_key(provider, endpoint),
            )

    @property
    def provider_id(self) -> str:
        return parse_endpoint_key(self._endpoint_key)[0]

    @property
    def endpoint_id(self) -> str:
        return parse_endpoint_key(self._endpoint_key)[1]

    @property
    def input(self) -> tuple[Modality, ...]:
        return self.capabilities.input

    @property
    def output(self) -> tuple[Modality, ...]:
        return self.capabilities.output

    @property
    def context_window(self) -> int | None:
        return self.capabilities.context_window

    @property
    def max_tokens(self) -> int | None:
        return self.capabilities.max_tokens

    @property
    def reasoning(self) -> bool:
        return self.capabilities.reasoning

    @property
    def supports_tool_use(self) -> bool:
        return self.capabilities.tool_use

    @property
    def supports_structured_output(self) -> bool:
        return self.capabilities.structured_output

    @property
    def supports_attachment(self) -> bool:
        return self.capabilities.attachment

    @property
    def supports_temperature(self) -> bool:
        return self.capabilities.temperature

    @property
    def supports_stream(self) -> bool:
        return self.capabilities.stream

    @property
    def supports_thinking(self) -> bool:
        return self.capabilities.supports_thinking

    @property
    def supports_image_input(self) -> bool:
        return self.capabilities.supports_image_input

    @property
    def supports_image_output(self) -> bool:
        return self.capabilities.supports_image_output

    def with_endpoint(self, endpoint: "Endpoint") -> "Model":
        inherits_auth = self.auth is None or self._auth_inherited
        auth = endpoint.auth if inherits_auth else self.auth
        endpoint_compat = endpoint.compat.merged(endpoint.protocol.to_compat()).merged(
            endpoint.dialect.to_compat()
        )
        endpoint_compat = Compat(
            items_by_key={
                key: value
                for key, value in endpoint_compat.items()
                if key != UPSTREAM_MODEL_ID
            }
        )
        model_transport_raw = self.transport.to_raw()
        model_transport_own_raw = (
            _copy_raw_mapping(self._transport_own_raw)
            if self._transport_own_raw is not None
            else None
        )
        if model_transport_own_raw is not None:
            model_transport_raw = model_transport_own_raw
        elif self._transport_legacy_raw is None:
            model_transport_own_raw = model_transport_raw
        model_routing_raw = self.routing.to_raw()
        model_routing_own_raw = (
            _copy_raw_mapping(self._routing_own_raw)
            if self._routing_own_raw is not None
            else None
        )
        if model_routing_own_raw is not None:
            model_routing_raw = model_routing_own_raw
        elif self._routing_legacy_raw is None:
            model_routing_own_raw = model_routing_raw
        transport = EndpointTransport.from_raw(
            _deep_merge_raw_mapping(endpoint.transport.to_raw(), model_transport_raw)
        )
        routing = EndpointRouting.from_raw(
            _deep_merge_raw_mapping(endpoint.routing.to_raw(), model_routing_raw)
        )
        return replace(
            self,
            _endpoint_key=endpoint.endpoint_key,
            api=endpoint.api,
            base_url=endpoint.base_url,
            base_url_env=endpoint.base_url_env,
            region=endpoint.region,
            lane=endpoint.lane,
            preferred_endpoint=endpoint.preferred,
            auth=auth,
            _auth_inherited=inherits_auth and auth is not None,
            compat=endpoint_compat.merged(self.compat),
            defaults=endpoint.defaults.merged(self.defaults),
            upstream_id=self.upstream_id,
            _upstream_id_legacy_raw=_copy_raw_mapping(self._upstream_id_legacy_raw)
            if self._upstream_id_legacy_raw is not None
            else None,
            transport=transport,
            _transport_own_raw=model_transport_own_raw,
            _transport_legacy_raw=_copy_raw_mapping(self._transport_legacy_raw)
            if self._transport_legacy_raw is not None
            else None,
            routing=routing,
            _routing_own_raw=model_routing_own_raw,
            _routing_legacy_raw=_copy_raw_mapping(self._routing_legacy_raw)
            if self._routing_legacy_raw is not None
            else None,
        )

    async def stream(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import stream

        return await stream(self, context, options=options, registry=registry)

    async def complete(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import complete

        return await complete(self, context, options=options, registry=registry)

    async def stream_simple(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import stream_simple

        return await stream_simple(self, context, options=options, registry=registry)

    async def complete_simple(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import complete_simple

        return await complete_simple(self, context, options=options, registry=registry)

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "displayName": self.name,
            "family": self.family,
            "alias": self.alias,
            "knowledge": self.knowledge,
            "releaseDate": self.release_date,
            "lastUpdated": self.last_updated,
            "compat": self.compat.to_raw(),
            "defaults": self.defaults.to_raw(),
        }
        raw.update(self.capabilities.to_raw())
        if self.pricing is not None:
            raw["pricing"] = self.pricing.to_raw()
        if self.auth is not None and not self._auth_inherited:
            raw["auth"] = self.auth.to_raw()
        if self.upstream_id is not None:
            if self._upstream_id_legacy_raw is not None:
                raw["compat"] = {
                    **cast(dict[str, object], raw["compat"]),
                    **_copy_raw_mapping(self._upstream_id_legacy_raw),
                }
            else:
                raw["upstreamId"] = self.upstream_id
        if (
            self._transport_legacy_raw is not None
            or self._routing_legacy_raw is not None
        ):
            raw["compat"] = {
                **cast(dict[str, object], raw["compat"]),
                **_legacy_transport_routing_compat_raw(
                    self._transport_legacy_raw,
                    self._routing_legacy_raw,
                ),
            }
        else:
            transport_raw = (
                _copy_raw_mapping(self._transport_own_raw)
                if self._transport_own_raw is not None
                else self.transport.to_raw()
            )
            if transport_raw:
                raw["transport"] = transport_raw
            routing_raw = (
                _copy_raw_mapping(self._routing_own_raw)
                if self._routing_own_raw is not None
                else self.routing.to_raw()
            )
            if routing_raw:
                raw["routing"] = routing_raw
        return {key: value for key, value in raw.items() if value is not None}


@dataclass(frozen=True)
class Endpoint:
    id: str
    api: str
    _provider_key: str = ""
    provider: InitVar[str | None] = None
    name: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    region: str | None = None
    lane: str | None = None
    preferred: bool = False
    docs: str | None = None
    auth: Auth | None = None
    _auth_inherited: bool = False
    compat: Compat = field(default_factory=Compat)
    defaults: Defaults = field(default_factory=Defaults)
    models: dict[str, Model] = field(default_factory=dict)
    protocol: EndpointProtocolFeatures = field(default_factory=EndpointProtocolFeatures)
    _protocol_explicit: bool = field(default=True, compare=False, repr=False)
    dialect: EndpointWireDialect = field(default_factory=EndpointWireDialect)
    _dialect_explicit: bool = field(default=True, compare=False, repr=False)
    _dialect_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    _dialect_raw_source: EndpointWireDialect | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    transport: EndpointTransport = field(default_factory=EndpointTransport)
    _transport_explicit: bool = field(default=True, compare=False, repr=False)
    _transport_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    _transport_raw_source: EndpointTransport | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    _transport_legacy_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    routing: EndpointRouting = field(default_factory=EndpointRouting)
    _routing_explicit: bool = field(default=True, compare=False, repr=False)
    _routing_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    _routing_raw_source: EndpointRouting | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    _routing_legacy_raw: dict[str, object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    def __post_init__(self, provider: str | None) -> None:
        if self._provider_key:
            return
        if provider is None:
            return
        object.__setattr__(self, "_provider_key", provider)

    @property
    def provider_id(self) -> str:
        return self._provider_key

    @property
    def endpoint_key(self) -> str:
        return build_endpoint_key(self.provider_id, self.id)

    def get_model(self, model_id: str) -> Model | None:
        return self.models.get(model_id)

    def list_models(self) -> list[Model]:
        return sorted(self.models.values(), key=lambda item: item.id)

    def bind_model(self, model: Model) -> Model:
        return model.with_endpoint(self)

    def to_raw(self) -> dict[str, object]:
        compat_raw = self.compat.to_raw()
        if (
            self._transport_legacy_raw is not None
            or self._routing_legacy_raw is not None
        ):
            compat_raw.update(
                _legacy_transport_routing_compat_raw(
                    self._transport_legacy_raw,
                    self._routing_legacy_raw,
                )
            )
        raw: dict[str, object] = {
            "api": self.api,
            "compat": compat_raw,
            "defaults": self.defaults.to_raw(),
            "models": {
                model_id: model.to_raw() for model_id, model in self.models.items()
            },
        }
        if self.name is not None:
            raw["displayName"] = self.name
        if self.base_url is not None:
            raw["baseUrl"] = self.base_url
        if self.base_url_env is not None:
            raw["baseUrlEnv"] = self.base_url_env
        if self.region is not None:
            raw["region"] = self.region
        if self.lane is not None:
            raw["lane"] = self.lane
        if self.preferred:
            raw["preferred"] = self.preferred
        if self.docs is not None:
            raw["docs"] = self.docs
        if self.auth is not None and not self._auth_inherited:
            raw["auth"] = self.auth.to_raw()
        if self._protocol_explicit and (protocol_raw := self.protocol.to_raw()):
            raw["protocol"] = protocol_raw
        if self._dialect_explicit:
            dialect_raw = (
                _copy_raw_mapping(self._dialect_raw)
                if self._dialect_raw is not None
                and self._dialect_raw_source == self.dialect
                else self.dialect.to_raw()
            )
            if dialect_raw:
                raw["dialect"] = dialect_raw
        if self._transport_legacy_raw is None and self._transport_explicit:
            transport_raw = (
                _copy_raw_mapping(self._transport_raw)
                if self._transport_raw is not None
                and self._transport_raw_source == self.transport
                else self.transport.to_raw()
            )
            if transport_raw:
                raw["transport"] = transport_raw
        if self._routing_legacy_raw is None and self._routing_explicit:
            routing_raw = (
                _copy_raw_mapping(self._routing_raw)
                if self._routing_raw is not None
                and self._routing_raw_source == self.routing
                else self.routing.to_raw()
            )
            if routing_raw:
                raw["routing"] = routing_raw
        return raw


@dataclass(frozen=True)
class Provider:
    id: str
    name: str | None = None
    website: str | None = None
    auth: Auth | None = None
    endpoints: dict[str, Endpoint] = field(default_factory=dict)

    def get_endpoint(self, endpoint_id: str) -> Endpoint | None:
        return self.endpoints.get(endpoint_id)

    def list_endpoints(self) -> list[Endpoint]:
        return sorted(self.endpoints.values(), key=lambda item: item.id)

    def get_model(self, endpoint_id: str, model_id: str) -> Model | None:
        endpoint = self.get_endpoint(endpoint_id)
        if endpoint is None:
            return None
        return endpoint.get_model(model_id)

    def list_models(self) -> list[Model]:
        models: list[Model] = []
        for endpoint in self.list_endpoints():
            models.extend(endpoint.list_models())
        return models

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "endpoints": {
                endpoint_id: endpoint.to_raw()
                for endpoint_id, endpoint in self.endpoints.items()
            }
        }
        if self.name is not None:
            raw["displayName"] = self.name
        if self.website is not None:
            raw["website"] = self.website
        if self.auth is not None:
            raw["auth"] = self.auth.to_raw()
        return raw


def _parse_modalities(raw: object) -> tuple[Modality, ...]:
    if isinstance(raw, str):
        values = tuple(
            value.strip()
            for value in raw.split(",")
            if value.strip() in ALLOWED_MODALITIES
        )
        return _coerce_modalities(values)
    if isinstance(raw, (list, tuple)):
        values = tuple(
            value.strip()
            for value in raw
            if isinstance(value, str) and value.strip() in ALLOWED_MODALITIES
        )
        return _coerce_modalities(values)
    return ("text",)


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _as_optional_number(value: object) -> float | int | None:
    return (
        value
        if not isinstance(value, bool)
        and isinstance(value, int | float)
        and isfinite(value)
        else None
    )


def _as_number(value: object) -> float | int:
    return value if isinstance(value, int | float) else 0


def _as_str_dict(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, entry in value.items():
        if isinstance(key, str) and isinstance(entry, str):
            result[key] = entry
    return result


def _as_optional_str_dict(value: object) -> dict[str, str | None]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str | None] = {}
    for key, entry in value.items():
        if isinstance(key, str) and (entry is None or isinstance(entry, str)):
            result[key] = entry
    return result


def _mapping_or_none(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _coerce_modalities(values: tuple[str, ...]) -> tuple[Modality, ...]:
    return tuple(
        cast(Modality, value) for value in values if value in ALLOWED_MODALITIES
    ) or ("text",)


def build_endpoint_key(provider_id: str, endpoint_id: str) -> str:
    return f"{provider_id}:{endpoint_id}"


def parse_endpoint_key(endpoint_key: str) -> tuple[str, str]:
    if ":" not in endpoint_key:
        return "", endpoint_key
    provider_id, endpoint_id = endpoint_key.split(":", 1)
    return provider_id, endpoint_id
