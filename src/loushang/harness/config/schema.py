from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass, replace
from typing import Any, Generic, Literal, TypeVar, cast

from loushang.harness.config.types import ConfigApplyResult, ConfigIssue

T = TypeVar("T")

ConfigFieldDecoder = Callable[[object, object], object]
ConfigFieldEncoder = Callable[[object, object], object]
ConfigFieldGetter = Callable[[T], object]
ConfigFieldReplacer = Callable[[T, object], T]
UnknownFieldPolicy = Literal["ignore", "issue", "error"]
RecoverableErrors = tuple[type[Exception], ...]


def _identity_decode(raw: object, current: object) -> object:
    del current
    return deepcopy(raw)


def _identity_encode(current: object, default: object) -> object:
    del default
    return deepcopy(current)


@dataclass(frozen=True)
class ConfigFieldSpec(Generic[T]):
    """Describe one Product field without moving its semantics into Harness."""

    attribute: str
    input_keys: tuple[str, ...] = ()
    output_key: str | None = None
    decode: ConfigFieldDecoder = _identity_decode
    encode: ConfigFieldEncoder = _identity_encode
    recover_errors: RecoverableErrors = ()
    getter: ConfigFieldGetter[T] | None = None
    replacer: ConfigFieldReplacer[T] | None = None

    def __post_init__(self) -> None:
        attribute = self.attribute.strip()
        if not attribute:
            raise ValueError("config field attribute must not be empty")
        object.__setattr__(self, "attribute", attribute)
        keys = self.input_keys or (attribute,)
        if any(not key.strip() for key in keys):
            raise ValueError("config field input keys must not be empty")
        if len(set(keys)) != len(keys):
            raise ValueError("config field input keys must be unique")
        output_key = self.output_key or keys[0]
        if not output_key.strip():
            raise ValueError("config field output key must not be empty")
        if output_key not in keys:
            keys = (output_key, *keys)
        object.__setattr__(self, "input_keys", tuple(keys))
        object.__setattr__(self, "output_key", output_key)

    def get(self, value: T) -> object:
        if self.getter is not None:
            return self.getter(value)
        return getattr(value, self.attribute)

    def replace(self, value: T, field_value: object) -> T:
        if self.replacer is not None:
            return self.replacer(value, field_value)
        if not is_dataclass(value):
            raise TypeError(
                f"config value for {self.attribute!r} must be a dataclass or provide a replacer"
            )
        return cast(T, replace(cast(Any, value), **{self.attribute: field_value}))


class SchemaConfigCodec(Generic[T]):
    """Compose a typed config from Product-owned declarative field rules."""

    def __init__(
        self,
        *,
        default_factory: Callable[[], T],
        fields: Sequence[ConfigFieldSpec[T]],
        removed_fields: Mapping[str, str] | None = None,
        unknown_fields: UnknownFieldPolicy = "ignore",
    ) -> None:
        if unknown_fields not in {"ignore", "issue", "error"}:
            raise ValueError(f"Unknown field policy: {unknown_fields}")
        self._default_factory = default_factory
        self._fields = tuple(fields)
        self._removed_fields = dict(removed_fields or {})
        self._unknown_fields = unknown_fields
        claimed: dict[str, str] = {}
        output_keys: dict[str, str] = {}
        for field in self._fields:
            for key in field.input_keys:
                previous = claimed.get(key)
                if previous is not None:
                    raise ValueError(
                        f"config input key {key!r} is claimed by {previous!r} and {field.attribute!r}"
                    )
                claimed[key] = field.attribute
            output_key = cast(str, field.output_key)
            previous_output = output_keys.get(output_key)
            if previous_output is not None:
                raise ValueError(
                    f"config output key {output_key!r} is claimed by "
                    f"{previous_output!r} and {field.attribute!r}"
                )
            output_keys[output_key] = field.attribute
        overlap = set(claimed).intersection(self._removed_fields)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"removed config fields also claim active keys: {names}")
        output_overlap = set(output_keys).intersection(self._removed_fields)
        if output_overlap:
            names = ", ".join(sorted(output_overlap))
            raise ValueError(f"removed config fields also claim output keys: {names}")
        self._claimed_keys = frozenset(claimed)

    def default(self) -> T:
        return self._default_factory()

    def encode(self, value: T) -> Mapping[str, object]:
        default = self._default_factory()
        patch: dict[str, object] = {}
        for field in self._fields:
            current = field.get(value)
            baseline = field.get(default)
            if current == baseline:
                continue
            patch[cast(str, field.output_key)] = deepcopy(
                field.encode(current, baseline)
            )
        return patch

    def apply(
        self,
        value: T,
        patch: Mapping[str, object],
        *,
        layer: str,
    ) -> ConfigApplyResult[T]:
        next_value = value
        issues: list[ConfigIssue] = []
        for key, message in self._removed_fields.items():
            if key not in patch:
                continue
            error = ValueError(message)
            issues.append(
                ConfigIssue(
                    layer=layer,
                    message=message,
                    error=error,
                    code="config_field_removed",
                    key=key,
                )
            )

        for field in self._fields:
            input_key = next(
                (key for key in field.input_keys if key in patch),
                None,
            )
            if input_key is None:
                continue
            current = field.get(next_value)
            try:
                decoded = field.decode(patch[input_key], current)
            except field.recover_errors as exc:
                issues.append(
                    ConfigIssue(
                        layer=layer,
                        message=str(exc),
                        error=exc,
                        code="config_field_invalid",
                        key=input_key,
                    )
                )
                continue
            next_value = field.replace(next_value, decoded)

        unknown = tuple(
            key
            for key in patch
            if key not in self._claimed_keys and key not in self._removed_fields
        )
        if unknown and self._unknown_fields == "error":
            raise ValueError(f"Unknown config settings: {', '.join(unknown)}")
        if self._unknown_fields == "issue":
            for key in unknown:
                error = ValueError(f"Unknown config setting: {key}")
                issues.append(
                    ConfigIssue(
                        layer=layer,
                        message=str(error),
                        error=error,
                        code="config_field_unknown",
                        key=key,
                    )
                )
        return ConfigApplyResult(value=next_value, issues=tuple(issues))


def decode_dataclass_patch(
    raw: object,
    current: object,
    *,
    field_name: str,
) -> object:
    if not isinstance(raw, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    if not is_dataclass(current):
        raise TypeError(f"{field_name} current value must be a dataclass")
    return replace(cast(Any, current), **dict(raw))


def encode_dataclass_diff(current: object, default: object) -> object:
    if not is_dataclass(current) or not is_dataclass(default):
        raise TypeError("dataclass diff values must be dataclasses")
    current_values = asdict(cast(Any, current))
    return {
        key: deepcopy(value)
        for key, value in current_values.items()
        if value != getattr(default, key)
    }


__all__ = [
    "ConfigFieldSpec",
    "RecoverableErrors",
    "SchemaConfigCodec",
    "UnknownFieldPolicy",
    "decode_dataclass_patch",
    "encode_dataclass_diff",
]
