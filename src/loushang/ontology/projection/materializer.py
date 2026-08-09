"""Pure bitemporal Fact-to-snapshot materialization."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from loushang.foundation.json import JSONValue, dump_json_value
from loushang.ontology.facts.model import (
    LinkAssertion,
    ObjectAssertion,
    PropertyAssertion,
)
from loushang.ontology.facts.ports import FactSelection, StoredFact
from loushang.ontology.projection.model import (
    ProjectedLink,
    ProjectedObject,
    ProjectedProperty,
    ProjectionSnapshot,
    ProjectionState,
)
from loushang.ontology.schema import (
    CompiledObjectTypeDefinition,
    CompiledOntologySchema,
    CompiledPropertyDefinition,
    LinkCardinality,
    ValueType,
)


@dataclass(frozen=True, slots=True)
class ProjectionDiagnostic:
    """Stable reason why selected facts cannot form a serving snapshot."""

    code: str
    path: str
    message: str


class ProjectionMaterializationError(ValueError):
    """Raised with every deterministic materialization diagnostic."""

    def __init__(self, diagnostics: tuple[ProjectionDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError(
                "ProjectionMaterializationError requires at least one diagnostic"
            )
        self.diagnostics = diagnostics
        super().__init__("; ".join(item.message for item in diagnostics))


def materialize_projection(
    selection: FactSelection,
    schema: CompiledOntologySchema,
    *,
    projection_version: int = 1,
    built_at: float | None = None,
) -> ProjectionSnapshot:
    """Build an immutable graph from one detached atomic Fact selection."""

    if not isinstance(selection, FactSelection):
        raise TypeError("materialize_projection requires a FactSelection")
    if type(projection_version) is not int or projection_version < 1:
        raise ValueError("projection_version must be a positive integer")
    selected = selection.facts
    valid_at = selection.valid_at
    recorded_at = selection.recorded_at
    built_at = recorded_at if built_at is None else _finite("built_at", built_at)
    diagnostics: list[ProjectionDiagnostic] = []
    object_type_facts: dict[UUID, set[str]] = {}
    property_facts: dict[tuple[UUID, str], list[StoredFact]] = {}
    link_facts: dict[tuple[UUID, str, UUID], list[StoredFact]] = {}

    for item in selected:
        assertion = item.fact.assertion
        if isinstance(assertion, ObjectAssertion):
            object_type_facts.setdefault(item.fact.subject_id, set()).add(
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

    resolved_types = _resolve_object_types(
        object_type_facts,
        schema,
        diagnostics,
    )
    resolved_properties = _resolve_property_facts(
        property_facts,
        resolved_types,
        schema,
        diagnostics,
    )
    _apply_defaults_and_required_properties(
        resolved_types,
        resolved_properties,
        schema,
        valid_at=valid_at,
        diagnostics=diagnostics,
    )
    _validate_unique_properties(
        resolved_types,
        resolved_properties,
        schema,
        diagnostics,
    )
    resolved_links = _resolve_link_facts(
        link_facts,
        resolved_types,
        schema,
        diagnostics,
    )
    _validate_link_integrity(
        resolved_types,
        resolved_links,
        schema,
        diagnostics,
    )
    if diagnostics:
        raise ProjectionMaterializationError(_sorted_diagnostics(diagnostics))

    objects = [
        ProjectedObject(
            object_id=object_id,
            object_type=object_type,
            properties=resolved_properties.get(object_id, {}).values(),
        )
        for object_id, object_type in resolved_types.items()
    ]
    state = ProjectionState(
        schema_version=str(schema.version),
        projection_version=projection_version,
        fact_watermark=selection.fact_watermark,
        valid_at=valid_at,
        recorded_at=recorded_at,
        built_at=built_at,
    )
    return ProjectionSnapshot(
        schema=schema,
        state=state,
        objects=objects,
        links=resolved_links,
        fact_ids=(item.fact.fact_id for item in selected),
    )


def _resolve_object_types(
    candidates: dict[UUID, set[str]],
    schema: CompiledOntologySchema,
    diagnostics: list[ProjectionDiagnostic],
) -> dict[UUID, str]:
    resolved: dict[UUID, str] = {}
    for subject_id, candidate_types in sorted(
        candidates.items(),
        key=lambda item: str(item[0]),
    ):
        path = f"objects.{subject_id}.type"
        if len(candidate_types) != 1:
            diagnostics.append(
                ProjectionDiagnostic(
                    "object_type_fact_conflict",
                    path,
                    f"conflicting object type facts for {subject_id}: "
                    f"{', '.join(sorted(candidate_types))}",
                )
            )
            continue
        candidate_type = next(iter(candidate_types))
        definition = schema.object_type(candidate_type)
        if definition is None:
            diagnostics.append(
                ProjectionDiagnostic(
                    "unknown_object_type",
                    path,
                    f"object type '{candidate_type}' is not declared by the schema",
                )
            )
            continue
        if definition.abstract:
            diagnostics.append(
                ProjectionDiagnostic(
                    "abstract_object_type",
                    path,
                    f"abstract object type '{candidate_type}' cannot be materialized",
                )
            )
            continue
        resolved[subject_id] = candidate_type
    return resolved


def _resolve_property_facts(
    candidates: dict[tuple[UUID, str], list[StoredFact]],
    resolved_types: dict[UUID, str],
    schema: CompiledOntologySchema,
    diagnostics: list[ProjectionDiagnostic],
) -> dict[UUID, dict[str, ProjectedProperty]]:
    resolved: dict[UUID, dict[str, ProjectedProperty]] = {}
    for (subject_id, property_name), values in sorted(
        candidates.items(),
        key=lambda item: (str(item[0][0]), item[0][1]),
    ):
        path = f"objects.{subject_id}.properties.{property_name}"
        subject_type = resolved_types.get(subject_id)
        if subject_type is None:
            diagnostics.append(
                ProjectionDiagnostic(
                    "property_subject_missing",
                    path,
                    f"property fact '{property_name}' has no projected object subject "
                    f"{subject_id}",
                )
            )
            continue
        declaration = _resolved_properties(schema, subject_type).get(property_name)
        if declaration is None:
            diagnostics.append(
                ProjectionDiagnostic(
                    "unknown_property",
                    path,
                    f"property '{property_name}' is not declared for object type "
                    f"'{subject_type}'",
                )
            )
            continue
        _, definition = declaration
        by_json = {
            dump_json_value(
                cast(PropertyAssertion, item.fact.assertion).value,
                name="fact property value",
                sort_keys=True,
            ): cast(PropertyAssertion, item.fact.assertion).value
            for item in values
        }
        if len(by_json) != 1:
            diagnostics.append(
                ProjectionDiagnostic(
                    "property_fact_conflict",
                    path,
                    f"conflicting property facts for {subject_id}.{property_name}",
                )
            )
            continue
        value = next(iter(by_json.values()))
        try:
            _validate_property_value(definition, value)
        except ValueError as exc:
            diagnostics.append(
                ProjectionDiagnostic(
                    "property_fact_value_invalid",
                    path,
                    str(exc),
                )
            )
            continue
        selected = min(values, key=lambda item: item.sequence)
        resolved.setdefault(subject_id, {})[property_name] = ProjectedProperty(
            name=property_name,
            value_type=definition.value_type,
            value=value,
            valid_from=selected.fact.valid_from,
            fact_id=selected.fact.fact_id,
            author_ref=selected.fact.author_ref,
            source_ref=selected.fact.source_ref,
        )
    return resolved


def _apply_defaults_and_required_properties(
    resolved_types: dict[UUID, str],
    resolved: dict[UUID, dict[str, ProjectedProperty]],
    schema: CompiledOntologySchema,
    *,
    valid_at: float,
    diagnostics: list[ProjectionDiagnostic],
) -> None:
    for object_id, object_type in sorted(
        resolved_types.items(),
        key=lambda item: str(item[0]),
    ):
        values = resolved.setdefault(object_id, {})
        for name, (_, definition) in _resolved_properties(schema, object_type).items():
            if name in values:
                continue
            default = definition.default
            if default is not None:
                try:
                    _validate_property_value(definition, default)
                except ValueError as exc:
                    diagnostics.append(
                        ProjectionDiagnostic(
                            "property_default_invalid",
                            f"objects.{object_id}.properties.{name}",
                            str(exc),
                        )
                    )
                    continue
                values[name] = ProjectedProperty(
                    name=name,
                    value_type=definition.value_type,
                    value=default,
                    valid_from=valid_at,
                    source_ref="ontology.schema.default",
                )
            elif definition.required:
                diagnostics.append(
                    ProjectionDiagnostic(
                        "required_property_missing",
                        f"objects.{object_id}.properties.{name}",
                        f"required property '{object_type}.{name}' is missing",
                    )
                )


def _validate_unique_properties(
    resolved_types: dict[UUID, str],
    resolved: dict[UUID, dict[str, ProjectedProperty]],
    schema: CompiledOntologySchema,
    diagnostics: list[ProjectionDiagnostic],
) -> None:
    seen: dict[tuple[str, str, str], UUID] = {}
    for object_id, object_type in sorted(
        resolved_types.items(),
        key=lambda item: str(item[0]),
    ):
        declarations = _resolved_properties(schema, object_type)
        for name, prop in resolved.get(object_id, {}).items():
            owner, definition = declarations[name]
            if not definition.unique:
                continue
            key = (
                owner,
                name,
                dump_json_value(prop.raw_value, sort_keys=True),
            )
            previous = seen.get(key)
            if previous is None:
                seen[key] = object_id
                continue
            diagnostics.append(
                ProjectionDiagnostic(
                    "unique_property_conflict",
                    f"objects.{object_id}.properties.{name}",
                    f"unique property '{owner}.{name}' is shared by "
                    f"{previous} and {object_id}",
                )
            )


def _resolve_link_facts(
    candidates: dict[tuple[UUID, str, UUID], list[StoredFact]],
    resolved_types: dict[UUID, str],
    schema: CompiledOntologySchema,
    diagnostics: list[ProjectionDiagnostic],
) -> list[ProjectedLink]:
    resolved: list[ProjectedLink] = []
    for (source_id, link_type, target_id), values in sorted(
        candidates.items(),
        key=lambda item: (str(item[0][0]), item[0][1], str(item[0][2])),
    ):
        path = f"objects.{source_id}.links.{link_type}.{target_id}"
        source_type = resolved_types.get(source_id)
        target_type = resolved_types.get(target_id)
        if source_type is None or target_type is None:
            missing_role = "source" if source_type is None else "target"
            diagnostics.append(
                ProjectionDiagnostic(
                    "link_endpoint_missing",
                    path,
                    f"link fact '{link_type}' has no projected {missing_role} object",
                )
            )
            continue
        definition = schema.link_type(link_type)
        if definition is None:
            diagnostics.append(
                ProjectionDiagnostic(
                    "unknown_link_type",
                    path,
                    f"link type '{link_type}' is not declared by the schema",
                )
            )
            continue
        if (
            source_type != definition.source_type
            or target_type != definition.target_type
        ):
            diagnostics.append(
                ProjectionDiagnostic(
                    "link_endpoint_type_invalid",
                    path,
                    f"link '{link_type}' requires {definition.source_type} -> "
                    f"{definition.target_type}, got {source_type} -> {target_type}",
                )
            )
            continue
        by_json = {
            dump_json_value(
                cast(LinkAssertion, item.fact.assertion).properties,
                name="fact link properties",
                sort_keys=True,
            ): cast(LinkAssertion, item.fact.assertion).properties
            for item in values
        }
        if len(by_json) != 1:
            diagnostics.append(
                ProjectionDiagnostic(
                    "link_fact_conflict",
                    path,
                    f"conflicting link facts for {source_id}.{link_type}.{target_id}",
                )
            )
            continue
        selected = min(values, key=lambda item: item.sequence)
        resolved.append(
            ProjectedLink(
                source_id=source_id,
                link_type=link_type,
                target_id=target_id,
                properties=next(iter(by_json.values())),
                valid_from=selected.fact.valid_from,
                fact_id=selected.fact.fact_id,
                source_ref=selected.fact.source_ref,
            )
        )
    return resolved


def _validate_link_integrity(
    resolved_types: dict[UUID, str],
    links: list[ProjectedLink],
    schema: CompiledOntologySchema,
    diagnostics: list[ProjectionDiagnostic],
) -> None:
    for definition in schema.link_types:
        matching = [link for link in links if link.link_type == definition.name]
        outgoing: dict[UUID, int] = {}
        incoming: dict[UUID, int] = {}
        for link in matching:
            outgoing[link.source_id] = outgoing.get(link.source_id, 0) + 1
            incoming[link.target_id] = incoming.get(link.target_id, 0) + 1
        if definition.cardinality in {
            LinkCardinality.ONE_TO_ONE,
            LinkCardinality.MANY_TO_ONE,
        }:
            for source_id, count in outgoing.items():
                if count > 1:
                    diagnostics.append(
                        ProjectionDiagnostic(
                            "link_cardinality_violation",
                            f"objects.{source_id}.links.{definition.name}",
                            f"link '{definition.name}' permits at most one outgoing target",
                        )
                    )
        if definition.cardinality in {
            LinkCardinality.ONE_TO_ONE,
            LinkCardinality.ONE_TO_MANY,
        }:
            for target_id, count in incoming.items():
                if count > 1:
                    diagnostics.append(
                        ProjectionDiagnostic(
                            "link_cardinality_violation",
                            f"objects.{target_id}.incoming.{definition.name}",
                            f"link '{definition.name}' permits at most one incoming source",
                        )
                    )
        if definition.required:
            for source_id, object_type in resolved_types.items():
                if object_type == definition.source_type and not outgoing.get(
                    source_id
                ):
                    diagnostics.append(
                        ProjectionDiagnostic(
                            "required_link_missing",
                            f"objects.{source_id}.links.{definition.name}",
                            f"required link '{definition.name}' is missing for {source_id}",
                        )
                    )


def _resolved_properties(
    schema: CompiledOntologySchema,
    object_type_name: str,
) -> dict[str, tuple[str, CompiledPropertyDefinition]]:
    resolved: dict[str, tuple[str, CompiledPropertyDefinition]] = {}
    visited: set[str] = set()

    def visit(object_type: CompiledObjectTypeDefinition) -> None:
        if object_type.name in visited:
            return
        visited.add(object_type.name)
        for parent_name in object_type.parent_types:
            parent = schema.object_type(parent_name)
            if parent is not None:
                visit(parent)
        for definition in object_type.properties:
            resolved[definition.name] = (object_type.name, definition)

    object_type = schema.object_type(object_type_name)
    if object_type is not None:
        visit(object_type)
    return resolved


def _validate_property_value(
    definition: CompiledPropertyDefinition,
    value: JSONValue,
) -> None:
    value_type = definition.value_type
    valid = True
    if value_type is ValueType.STRING:
        valid = isinstance(value, str)
    elif value_type is ValueType.INTEGER:
        valid = type(value) is int
    elif value_type is ValueType.NUMBER:
        valid = type(value) in (int, float) and math.isfinite(
            float(cast(int | float, value))
        )
    elif value_type is ValueType.BOOLEAN:
        valid = type(value) is bool
    elif value_type is ValueType.DATETIME:
        valid = isinstance(value, str)
        if valid:
            try:
                datetime.fromisoformat(cast(str, value))
            except ValueError:
                valid = False
    elif value_type is ValueType.JSON:
        valid = True
    if not valid:
        raise ValueError(
            f"property '{definition.name}' requires a {value_type.value} value"
        )


def _finite(name: str, value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(
        float(cast(int | float, value))
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(cast(int | float, value))


def _sorted_diagnostics(
    diagnostics: list[ProjectionDiagnostic],
) -> tuple[ProjectionDiagnostic, ...]:
    return tuple(
        sorted(diagnostics, key=lambda item: (item.path, item.code, item.message))
    )


__all__ = [
    "ProjectionDiagnostic",
    "ProjectionMaterializationError",
    "materialize_projection",
]
