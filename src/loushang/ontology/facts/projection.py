"""Deterministic bitemporal Fact-to-object projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from loushang.foundation.json import JSONValue, dump_json_value
from loushang.ontology.core.object import OntologyObject, PropertyVersion
from loushang.ontology.core.projection import ProjectionState
from loushang.ontology.core.store import ObjectStore
from loushang.ontology.core.store_port import OntologyReadStore
from loushang.ontology.facts.model import (
    LinkAssertion,
    ObjectAssertion,
    PropertyAssertion,
)
from loushang.ontology.facts.store import FactReadStore, StoredFact
from loushang.ontology.schema import (
    CompiledObjectTypeDefinition,
    CompiledOntologySchema,
    CompiledPropertyDefinition,
    ValueType,
)


@dataclass(frozen=True, slots=True)
class FactProjectionDiagnostic:
    """Stable reason why a fact selection cannot become a serving graph."""

    code: str
    path: str
    message: str


class FactProjectionError(ValueError):
    """Raised with all deterministic fact-projection diagnostics."""

    def __init__(self, diagnostics: tuple[FactProjectionDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("FactProjectionError requires at least one diagnostic")
        self.diagnostics = diagnostics
        super().__init__("; ".join(item.message for item in diagnostics))


@dataclass(frozen=True, slots=True)
class FactProjection:
    """One detached object/link graph built from an explicit bitemporal view."""

    view: OntologyReadStore
    schema_version: str
    source_fact_watermark: int
    valid_at: float
    recorded_at: float
    fact_ids: tuple[UUID, ...]


class _ReadOnlyProjection:
    """Capability wrapper that exposes no projection-builder mutation methods."""

    __slots__ = ("__store",)

    def __init__(self, store: ObjectStore) -> None:
        self.__store = store

    @property
    def schema(self) -> CompiledOntologySchema | None:
        return self.__store.schema

    @property
    def projection_state(self) -> ProjectionState:
        return self.__store.projection_state

    def get(self, obj_id: UUID) -> OntologyObject | None:
        return self.__store.get(obj_id)

    def get_by_type(self, object_type: str) -> list[OntologyObject]:
        return self.__store.get_by_type(object_type)

    def find_neighbors(
        self,
        obj_id: UUID,
        link_type: str,
        direction: str = "outgoing",
        as_of: float | None = None,
        active_only: bool = True,
    ) -> list[OntologyObject]:
        return self.__store.find_neighbors(
            obj_id,
            link_type,
            direction=direction,
            as_of=as_of,
            active_only=active_only,
        )

    def all_objects(self) -> list[OntologyObject]:
        return self.__store.all_objects()


def project_facts(
    facts: FactReadStore,
    schema: CompiledOntologySchema,
    *,
    valid_at: float,
    recorded_at: float,
) -> FactProjection:
    """Build a schema-validated graph without mutating the semantic FactStore."""

    selected = facts.facts_as_of(valid_at=valid_at, recorded_at=recorded_at)
    diagnostics: list[FactProjectionDiagnostic] = []
    object_types: dict[UUID, set[str]] = {}
    property_facts: dict[tuple[UUID, str], list[StoredFact]] = {}
    link_facts: dict[tuple[UUID, str, UUID], list[StoredFact]] = {}

    for item in selected:
        assertion = item.fact.assertion
        if isinstance(assertion, ObjectAssertion):
            object_types.setdefault(item.fact.subject_id, set()).add(
                assertion.object_type
            )
        elif isinstance(assertion, PropertyAssertion):
            property_facts.setdefault(
                (item.fact.subject_id, assertion.property_name),
                [],
            ).append(item)
        elif isinstance(assertion, LinkAssertion):
            link_facts.setdefault(
                (item.fact.subject_id, assertion.link_type, assertion.target_id),
                [],
            ).append(item)

    resolved_types: dict[UUID, str] = {}
    for subject_id, candidate_types in sorted(
        object_types.items(),
        key=lambda item: str(item[0]),
    ):
        if len(candidate_types) != 1:
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="object_type_fact_conflict",
                    path=f"objects.{subject_id}.type",
                    message=(
                        f"conflicting object type facts for {subject_id}: "
                        f"{', '.join(sorted(candidate_types))}"
                    ),
                )
            )
            continue
        candidate_type = next(iter(candidate_types))
        if schema.object_type(candidate_type) is None:
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="unknown_object_type",
                    path=f"objects.{subject_id}.type",
                    message=f"object type '{candidate_type}' is not declared by the schema",
                )
            )
            continue
        resolved_types[subject_id] = candidate_type

    resolved_properties: dict[UUID, dict[str, tuple[object, StoredFact]]] = {}
    for (subject_id, property_name), property_candidates in sorted(
        property_facts.items(),
        key=lambda item: (str(item[0][0]), item[0][1]),
    ):
        subject_type = resolved_types.get(subject_id)
        if subject_type is None:
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="property_subject_missing",
                    path=f"objects.{subject_id}.properties.{property_name}",
                    message=(
                        f"property fact '{property_name}' has no projected object subject "
                        f"{subject_id}"
                    ),
                )
            )
            continue
        property_definition = _resolved_property(schema, subject_type, property_name)
        if property_definition is None:
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="unknown_property",
                    path=f"objects.{subject_id}.properties.{property_name}",
                    message=(
                        f"property '{property_name}' is not declared for object type "
                        f"'{subject_type}'"
                    ),
                )
            )
            continue
        values_by_json = {
            dump_json_value(
                cast(PropertyAssertion, item.fact.assertion).value,
                name="fact property value",
                sort_keys=True,
            ): cast(PropertyAssertion, item.fact.assertion).value
            for item in property_candidates
        }
        if len(values_by_json) != 1:
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="property_fact_conflict",
                    path=f"objects.{subject_id}.properties.{property_name}",
                    message=(
                        f"conflicting property facts for {subject_id}.{property_name}"
                    ),
                )
            )
            continue
        selected_value = next(iter(values_by_json.values()))
        selected_fact = min(property_candidates, key=lambda item: item.sequence)
        try:
            runtime_value = _runtime_value(property_definition, selected_value)
        except (TypeError, ValueError) as exc:
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="property_fact_value_invalid",
                    path=f"objects.{subject_id}.properties.{property_name}",
                    message=str(exc),
                )
            )
            continue
        resolved_properties.setdefault(subject_id, {})[property_name] = (
            runtime_value,
            selected_fact,
        )

    resolved_links: list[
        tuple[UUID, str, UUID, dict[str, JSONValue], StoredFact]
    ] = []
    for (source_id, link_type, target_id), link_candidates in sorted(
        link_facts.items(),
        key=lambda item: (str(item[0][0]), item[0][1], str(item[0][2])),
    ):
        source_type = resolved_types.get(source_id)
        target_type = resolved_types.get(target_id)
        if source_type is None or target_type is None:
            missing_role = "source" if source_type is None else "target"
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="link_endpoint_missing",
                    path=f"objects.{source_id}.links.{link_type}.{target_id}",
                    message=(
                        f"link fact '{link_type}' has no projected {missing_role} object"
                    ),
                )
            )
            continue
        link_definition = schema.link_type(link_type)
        if link_definition is None:
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="unknown_link_type",
                    path=f"objects.{source_id}.links.{link_type}",
                    message=f"link type '{link_type}' is not declared by the schema",
                )
            )
            continue
        if (
            source_type != link_definition.source_type
            or target_type != link_definition.target_type
        ):
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="link_endpoint_type_invalid",
                    path=f"objects.{source_id}.links.{link_type}.{target_id}",
                    message=(
                        f"link '{link_type}' requires {link_definition.source_type} -> "
                        f"{link_definition.target_type}, got {source_type} -> {target_type}"
                    ),
                )
            )
            continue
        properties_by_json = {
            dump_json_value(
                cast(LinkAssertion, item.fact.assertion).properties,
                name="fact link properties",
                sort_keys=True,
            ): cast(LinkAssertion, item.fact.assertion).properties
            for item in link_candidates
        }
        if len(properties_by_json) != 1:
            diagnostics.append(
                FactProjectionDiagnostic(
                    code="link_fact_conflict",
                    path=f"objects.{source_id}.links.{link_type}.{target_id}",
                    message=(
                        f"conflicting link facts for {source_id}.{link_type}.{target_id}"
                    ),
                )
            )
            continue
        resolved_links.append(
            (
                source_id,
                link_type,
                target_id,
                next(iter(properties_by_json.values())),
                min(link_candidates, key=lambda item: item.sequence),
            )
        )

    if diagnostics:
        raise FactProjectionError(_sorted_diagnostics(diagnostics))

    store = ObjectStore()
    store.bind_schema(schema)
    try:
        for subject_id, object_type in sorted(
            resolved_types.items(),
            key=lambda item: str(item[0]),
        ):
            property_entries = resolved_properties.get(subject_id, {})
            store.create(
                object_type,
                {name: item[0] for name, item in property_entries.items()},
                obj_id=subject_id,
            )
            projected = store.get(subject_id)
            assert projected is not None
            for name, versions in projected._properties.items():
                property_entry = property_entries.get(name)
                if property_entry is None:
                    versions[-1] = PropertyVersion(
                        value=versions[-1].value,
                        timestamp=float(valid_at),
                        source="ontology.schema.default",
                    )
                    continue
                value, stored_fact = property_entry
                versions[-1] = PropertyVersion(
                    value=value,
                    timestamp=stored_fact.fact.valid_from,
                    author=stored_fact.fact.author_ref,
                    source=stored_fact.fact.source_ref,
                )
        for source_id, link_type, target_id, properties, stored_fact in resolved_links:
            source = store.get(source_id)
            target = store.get(target_id)
            assert source is not None
            assert target is not None
            store.link_objects(
                source,
                link_type,
                target,
                timestamp=stored_fact.fact.valid_from,
                properties=properties,
            )
    except (TypeError, ValueError) as exc:
        raise FactProjectionError(
            (
                FactProjectionDiagnostic(
                    code="fact_projection_invalid",
                    path="$",
                    message=str(exc),
                ),
            )
        ) from exc

    integrity = store.validate_integrity()
    if integrity:
        raise FactProjectionError(
            tuple(
                FactProjectionDiagnostic(
                    code=item.code,
                    path=item.path,
                    message=item.message,
                )
                for item in integrity
            )
        )
    store._mutations = []
    store._watermark = 0
    store._projected_watermark = 0
    store._projection_version = 1
    store._projection_built_at = float(recorded_at)
    store._seal_projection()
    return FactProjection(
        view=_ReadOnlyProjection(store),
        schema_version=str(schema.version),
        source_fact_watermark=facts.fact_watermark,
        valid_at=float(valid_at),
        recorded_at=float(recorded_at),
        fact_ids=tuple(item.fact.fact_id for item in selected),
    )


def _resolved_property(
    schema: CompiledOntologySchema,
    object_type_name: str,
    property_name: str,
) -> CompiledPropertyDefinition | None:
    visited: set[str] = set()

    def visit(object_type: CompiledObjectTypeDefinition) -> CompiledPropertyDefinition | None:
        own = object_type.property(property_name)
        if own is not None:
            return own
        if object_type.name in visited:
            return None
        visited.add(object_type.name)
        for parent_name in reversed(object_type.parent_types):
            parent = schema.object_type(parent_name)
            if parent is not None and (resolved := visit(parent)) is not None:
                return resolved
        return None

    object_type = schema.object_type(object_type_name)
    return None if object_type is None else visit(object_type)


def _runtime_value(
    definition: CompiledPropertyDefinition,
    value: JSONValue,
) -> object:
    if definition.value_type is not ValueType.DATETIME:
        return value
    if not isinstance(value, str):
        raise ValueError(
            f"datetime property '{definition.name}' requires an ISO 8601 string fact value"
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"datetime property '{definition.name}' has an invalid ISO 8601 value"
        ) from exc


def _sorted_diagnostics(
    diagnostics: list[FactProjectionDiagnostic],
) -> tuple[FactProjectionDiagnostic, ...]:
    return tuple(sorted(diagnostics, key=lambda item: (item.path, item.code, item.message)))


__all__ = [
    "FactProjection",
    "FactProjectionDiagnostic",
    "FactProjectionError",
    "project_facts",
]
