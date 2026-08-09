"""Immutable contracts for mapped source snapshots selected by a Product."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast
from uuid import UUID

from loushang.foundation.json import JSONValue, dump_json_value


def _non_empty_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _finite(name: str, value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(
        float(cast(int | float, value))
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(cast(int | float, value))


@dataclass(frozen=True, slots=True)
class SourceInputRevision:
    """One coordinate in a materialization source revision vector."""

    binding_id: str
    mapping_version: str
    source_revision: str

    def __post_init__(self) -> None:
        for name in ("binding_id", "mapping_version", "source_revision"):
            _non_empty_text(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class SourceBinding:
    """Bind source-owned schema states to one versioned Product mapping.

    Targets are package-local stable semantic IDs, never renameable API names.
    This contract identifies authority; it contains no connector or scheduler.
    """

    binding_id: str
    mapping_version: str
    object_existence_ids: tuple[str, ...] = ()
    property_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty_text("binding_id", self.binding_id)
        _non_empty_text("mapping_version", self.mapping_version)
        for name in ("object_existence_ids", "property_ids"):
            raw = tuple(getattr(self, name))
            if any(not isinstance(item, str) for item in raw):
                raise TypeError(f"{name} must contain strings")
            values = tuple(sorted(raw))
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, values)
        if not self.object_existence_ids and not self.property_ids:
            raise ValueError(
                "source binding must declare at least one authority target"
            )


@dataclass(frozen=True, slots=True, init=False)
class MappedSourceProperty:
    """One source field already mapped to a stable ontology property ID."""

    property_id: str
    field_ref: str
    valid_from: float
    _value_json: str = field(repr=False)

    def __init__(
        self,
        *,
        property_id: str,
        value: object,
        field_ref: str,
        valid_from: float,
    ) -> None:
        object.__setattr__(
            self, "property_id", _non_empty_text("property_id", property_id)
        )
        object.__setattr__(self, "field_ref", _non_empty_text("field_ref", field_ref))
        object.__setattr__(self, "valid_from", _finite("valid_from", valid_from))
        object.__setattr__(
            self,
            "_value_json",
            dump_json_value(value, name="mapped source property value", sort_keys=True),
        )

    @property
    def raw_value(self) -> JSONValue:
        return cast(JSONValue, json.loads(self._value_json))


@dataclass(frozen=True, slots=True, init=False)
class MappedSourceObject:
    """One canonical object identity selected by an application mapping."""

    object_id: UUID
    object_type_id: str
    source_record_ref: str
    _properties: tuple[MappedSourceProperty, ...] = field(repr=False)

    def __init__(
        self,
        *,
        object_id: UUID,
        object_type_id: str,
        source_record_ref: str,
        properties: Iterable[MappedSourceProperty] = (),
    ) -> None:
        if not isinstance(object_id, UUID):
            raise TypeError("object_id must be a UUID")
        raw_properties = tuple(properties)
        if any(not isinstance(item, MappedSourceProperty) for item in raw_properties):
            raise TypeError("properties must contain MappedSourceProperty values")
        values = tuple(sorted(raw_properties, key=lambda item: item.property_id))
        ids = [item.property_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("mapped source object contains duplicate properties")
        object.__setattr__(self, "object_id", object_id)
        object.__setattr__(
            self,
            "object_type_id",
            _non_empty_text("object_type_id", object_type_id),
        )
        object.__setattr__(
            self,
            "source_record_ref",
            _non_empty_text("source_record_ref", source_record_ref),
        )
        object.__setattr__(self, "_properties", values)

    @property
    def properties(self) -> tuple[MappedSourceProperty, ...]:
        return self._properties


@dataclass(frozen=True, slots=True, init=False)
class MappedSourceSnapshot:
    """A complete immutable mapped snapshot for one source binding revision."""

    _objects: tuple[MappedSourceObject, ...] = field(repr=False)

    def __init__(self, *, objects: Iterable[MappedSourceObject] = ()) -> None:
        raw_objects = tuple(objects)
        if any(not isinstance(item, MappedSourceObject) for item in raw_objects):
            raise TypeError("objects must contain MappedSourceObject values")
        values = tuple(sorted(raw_objects, key=lambda item: str(item.object_id)))
        ids = [item.object_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("mapped source snapshot contains duplicate object IDs")
        object.__setattr__(self, "_objects", values)

    @property
    def objects(self) -> tuple[MappedSourceObject, ...]:
        return self._objects


@dataclass(frozen=True, slots=True)
class MappedSourceInput:
    """One reproducible mapped snapshot selected for materialization.

    Change-set payloads are intentionally deferred until a base-revision chain
    contract is implemented; this first slice never presents a delta as a full
    snapshot.
    """

    binding_id: str
    mapping_version: str
    source_revision: str
    payload: MappedSourceSnapshot

    def __post_init__(self) -> None:
        for name in ("binding_id", "mapping_version", "source_revision"):
            _non_empty_text(name, getattr(self, name))
        if not isinstance(self.payload, MappedSourceSnapshot):
            raise TypeError("payload must be a MappedSourceSnapshot")

    @property
    def revision(self) -> SourceInputRevision:
        return SourceInputRevision(
            self.binding_id,
            self.mapping_version,
            self.source_revision,
        )


__all__ = [
    "MappedSourceInput",
    "MappedSourceObject",
    "MappedSourceProperty",
    "MappedSourceSnapshot",
    "SourceBinding",
    "SourceInputRevision",
]
