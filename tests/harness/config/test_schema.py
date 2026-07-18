from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from loushang.harness.config import ConfigFieldSpec, SchemaConfigCodec


@dataclass(frozen=True)
class _Config:
    name: str = "default"
    limit: int = 10
    enabled: bool = True
    note: str | None = "default-note"
    tags: tuple[str, ...] = ("default-tag",)


def _string(raw: object, current: object) -> str:
    del current
    if not isinstance(raw, str):
        raise TypeError("expected a string")
    return raw


def _integer(raw: object, current: object) -> int:
    del current
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise TypeError("expected an integer")
    return raw


def _boolean(raw: object, current: object) -> bool:
    del current
    if not isinstance(raw, bool):
        raise TypeError("expected a boolean")
    return raw


def _identity(current: object, default: object) -> object:
    del default
    return current


def _codec(
    *,
    recover_limit_errors: tuple[type[Exception], ...] = (TypeError, ValueError),
) -> SchemaConfigCodec[_Config]:
    return SchemaConfigCodec(
        default_factory=_Config,
        fields=(
            ConfigFieldSpec(
                attribute="name",
                input_keys=("name", "legacyName"),
                output_key="name",
                decode=_string,
                encode=_identity,
                recover_errors=(),
            ),
            ConfigFieldSpec(
                attribute="limit",
                input_keys=("limit",),
                output_key="limit",
                decode=_integer,
                encode=_identity,
                recover_errors=recover_limit_errors,
            ),
            ConfigFieldSpec(
                attribute="enabled",
                input_keys=("enabled",),
                output_key="enabled",
                decode=_boolean,
                encode=_identity,
                recover_errors=(TypeError, ValueError),
            ),
            ConfigFieldSpec(
                attribute="note",
                input_keys=("note",),
                output_key="note",
                decode=lambda raw, current: raw,
                encode=_identity,
                recover_errors=(),
            ),
            ConfigFieldSpec(
                attribute="tags",
                input_keys=("tags",),
                output_key="tags",
                decode=lambda raw, current: raw,
                encode=lambda current, default: list(current),
                recover_errors=(),
            ),
        ),
        removed_fields={"transport": "transport is no longer supported"},
    )


def test_schema_config_codec_reads_alias_and_prefers_canonical_input_key() -> None:
    codec = _codec()

    aliased = codec.apply(
        codec.default(),
        {"legacyName": "legacy"},
        layer="global",
    )
    canonical = codec.apply(
        codec.default(),
        {"name": "canonical", "legacyName": "legacy"},
        layer="project",
    )

    assert aliased.value == _Config(name="legacy")
    assert aliased.issues == ()
    assert canonical.value == _Config(name="canonical")
    assert canonical.issues == ()


def test_schema_config_codec_writes_only_changed_canonical_fields() -> None:
    codec = _codec()

    assert codec.encode(_Config()) == {}
    assert codec.encode(_Config(name="custom", enabled=False)) == {
        "name": "custom",
        "enabled": False,
    }


def test_schema_config_codec_always_reads_its_declared_output_key() -> None:
    codec = SchemaConfigCodec(
        default_factory=_Config,
        fields=(
            ConfigFieldSpec(
                attribute="name",
                input_keys=("legacyName",),
                output_key="canonicalName",
                decode=_string,
                encode=_identity,
            ),
        ),
        unknown_fields="error",
    )
    expected = _Config(name="custom")

    encoded = codec.encode(expected)
    decoded = codec.apply(codec.default(), encoded, layer="project")

    assert encoded == {"canonicalName": "custom"}
    assert decoded.value == expected
    assert decoded.issues == ()


def test_schema_config_codec_preserves_non_default_null_and_empty_values() -> None:
    codec = _codec()

    assert codec.encode(_Config(note=None, tags=())) == {
        "note": None,
        "tags": [],
    }


def test_schema_config_codec_reports_removed_fields_and_applies_valid_fields() -> None:
    codec = _codec()

    result = codec.apply(
        codec.default(),
        {"transport": "websocket", "name": "valid"},
        layer="session",
    )

    assert result.value == _Config(name="valid")
    assert len(result.issues) == 1
    assert result.issues[0].layer == "session"
    assert isinstance(result.issues[0].error, Exception)


def test_schema_config_codec_recovers_one_field_without_dropping_valid_siblings() -> (
    None
):
    codec = _codec()
    current = _Config(name="before", limit=20, enabled=True)

    result = codec.apply(
        current,
        {"name": "after", "limit": "invalid", "enabled": False},
        layer="project",
    )

    assert result.value == _Config(name="after", limit=20, enabled=False)
    assert len(result.issues) == 1
    assert result.issues[0].layer == "project"
    assert isinstance(result.issues[0].error, TypeError)


def test_schema_config_codec_propagates_non_recoverable_field_errors() -> None:
    codec = _codec(recover_limit_errors=(ValueError,))

    with pytest.raises(TypeError):
        codec.apply(codec.default(), {"limit": "invalid"}, layer="global")


def test_schema_config_codec_does_not_recover_replacer_errors() -> None:
    def broken_replacer(value: _Config, field_value: object) -> _Config:
        del value, field_value
        raise TypeError("broken replacer")

    codec = SchemaConfigCodec(
        default_factory=_Config,
        fields=(
            ConfigFieldSpec(
                attribute="name",
                decode=_string,
                encode=_identity,
                recover_errors=(TypeError,),
                replacer=broken_replacer,
            ),
        ),
        removed_fields={},
    )

    with pytest.raises(TypeError):
        codec.apply(codec.default(), {"name": "valid"}, layer="global")


def test_schema_config_codec_ignores_unknown_fields_by_default() -> None:
    codec = _codec()

    result = codec.apply(
        codec.default(),
        {"unknown": {"nested": True}},
        layer="global",
    )

    assert result.value == _Config()
    assert result.issues == ()


def test_schema_config_codec_does_not_mutate_input_patch() -> None:
    codec = _codec()
    patch: Mapping[str, object] = {"legacyName": "legacy", "unknown": ["value"]}

    codec.apply(codec.default(), patch, layer="global")

    assert patch == {"legacyName": "legacy", "unknown": ["value"]}
