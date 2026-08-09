"""Materialize immutable runtime types from a compiled ontology schema."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeAlias

from loushang.ontology.core.link_type import Cardinality, LinkType
from loushang.ontology.core.object_type import ObjectType
from loushang.ontology.core.property import Property
from loushang.ontology.schema import (
    CompiledOntologySchema,
    LinkCardinality,
    ValueType,
)

PropertyValidator: TypeAlias = Callable[[Any], bool]
PropertyValidatorKey: TypeAlias = tuple[str, str]
PropertyValidators: TypeAlias = Mapping[PropertyValidatorKey, PropertyValidator]

_RUNTIME_VALUE_TYPES: dict[ValueType, type | str] = {
    ValueType.STRING: str,
    ValueType.INTEGER: int,
    ValueType.NUMBER: float,
    ValueType.BOOLEAN: bool,
    ValueType.DATETIME: datetime,
    ValueType.JSON: "json",
}

_RUNTIME_CARDINALITIES = {
    LinkCardinality.ONE_TO_ONE: Cardinality.ONE_TO_ONE,
    LinkCardinality.ONE_TO_MANY: Cardinality.ONE_TO_MANY,
    LinkCardinality.MANY_TO_ONE: Cardinality.MANY_TO_ONE,
    LinkCardinality.MANY_TO_MANY: Cardinality.MANY_TO_MANY,
}


@dataclass(frozen=True, slots=True)
class MaterializedOntologySchema:
    """Runtime definitions detached from draft compatibility objects."""

    object_types: tuple[ObjectType, ...]
    link_types: tuple[LinkType, ...]


def materialize_compiled_schema(
    schema: CompiledOntologySchema,
    *,
    property_validators: PropertyValidators | None = None,
) -> MaterializedOntologySchema:
    """Build runtime definitions exclusively from ``schema``.

    Python validators are an optional local compatibility overlay. They are
    intentionally absent from the portable compiled schema and its JSON form.
    """

    validators = property_validators or {}
    object_types = tuple(
        ObjectType(
            name=object_type.name,
            properties=[
                Property(
                    name=prop.name,
                    data_type=_RUNTIME_VALUE_TYPES[prop.value_type],
                    required=prop.required,
                    unique=prop.unique,
                    indexed=prop.indexed,
                    default=prop.default,
                    validator=validators.get((object_type.name, prop.name)),
                    description=prop.description,
                )
                for prop in object_type.properties
            ],
            parent_types=list(object_type.parent_types),
            interfaces=list(object_type.interfaces),
            abstract=object_type.abstract,
            icon=object_type.icon,
            description=object_type.description,
            display_name_property=object_type.display_name_property,
        )
        for object_type in schema.object_types
    )
    object_types_by_name = {object_type.name: object_type for object_type in object_types}

    link_types = tuple(
        LinkType(
            name=link_type.name,
            source_type=link_type.source_type,
            target_type=link_type.target_type,
            cardinality=_RUNTIME_CARDINALITIES[link_type.cardinality],
            required=link_type.required,
            inverse_name=link_type.inverse_name,
            temporal=link_type.temporal,
            description=link_type.description,
        )
        for link_type in schema.link_types
    )
    for link_type in link_types:
        object_types_by_name[link_type.source_type].add_outgoing_link_type(link_type.name)
        object_types_by_name[link_type.target_type].add_incoming_link_type(link_type.name)
    for object_type in object_types:
        object_type.freeze_schema()

    return MaterializedOntologySchema(object_types=object_types, link_types=link_types)


__all__ = [
    "MaterializedOntologySchema",
    "PropertyValidator",
    "PropertyValidatorKey",
    "PropertyValidators",
    "materialize_compiled_schema",
]
