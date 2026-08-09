"""Reference evaluator for typed ontology query requests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from loushang.ontology.core.object import OntologyObject
from loushang.ontology.core.store_port import OntologyReadStore
from loushang.ontology.query.contracts import (
    AsOf,
    Limit,
    ObjectTypeFilter,
    Offset,
    PropertyFilter,
    QueryDiagnostic,
    QueryRequest,
    QueryResult,
    SortBy,
    StartAll,
    StartFromIds,
    StartFromType,
    Traverse,
)


def execute_query(store: OntologyReadStore, request: QueryRequest) -> QueryResult:
    """Evaluate a request against one sealed object projection."""

    current_version = str(store.schema.version) if store.schema is not None else None
    if request.schema_version is not None and request.schema_version != current_version:
        return QueryResult(
            object_ids=(),
            schema_version=current_version,
            projection=store.projection_state,
            diagnostics=(
                QueryDiagnostic(
                    code="schema_version_mismatch",
                    message=(
                        f"Query requires schema {request.schema_version}; "
                        f"store provides {current_version or 'no schema'}"
                    ),
                ),
            ),
        )

    result: list[OntologyObject] = []
    as_of: float | None = None
    for step in request.steps:
        if isinstance(step, StartFromIds):
            result = [obj for object_id in step.object_ids if (obj := store.get(object_id))]
        elif isinstance(step, StartFromType):
            result = store.get_by_type(step.object_type)
        elif isinstance(step, StartAll):
            result = store.all_objects()
        elif isinstance(step, Traverse):
            result = _traverse(store, result, step, as_of=as_of)
        elif isinstance(step, PropertyFilter):
            result = _filter_by_property(
                result,
                step.property_name,
                step.operator,
                step.value,
                as_of=as_of,
            )
        elif isinstance(step, ObjectTypeFilter):
            result = [obj for obj in result if obj.object_type == step.object_type]
        elif isinstance(step, AsOf):
            as_of = step.timestamp
        elif isinstance(step, Limit):
            result = result[: step.count]
        elif isinstance(step, Offset):
            result = result[step.count :]
        elif isinstance(step, SortBy):
            result.sort(
                key=lambda obj: _sort_key(obj.get(step.property_name, as_of=as_of)),
                reverse=not step.ascending,
            )

    return QueryResult(
        object_ids=tuple(obj.id for obj in result),
        schema_version=current_version,
        projection=store.projection_state,
    )


def _traverse(
    store: OntologyReadStore,
    objects: list[OntologyObject],
    step: Traverse,
    *,
    as_of: float | None,
) -> list[OntologyObject]:
    result: list[OntologyObject] = []
    seen: set[UUID] = set()
    for obj in objects:
        for neighbor in store.find_neighbors(
            obj.id,
            step.link_type,
            direction=step.direction,
            as_of=as_of,
        ):
            if neighbor.id not in seen:
                seen.add(neighbor.id)
                result.append(neighbor)
    return result


def _filter_by_property(
    objects: list[OntologyObject],
    prop: str,
    op: str,
    value: object,
    *,
    as_of: float | None,
) -> list[OntologyObject]:
    operators: dict[str, Callable[[Any, Any], bool]] = {
        "==": lambda left, right: left == right,
        "!=": lambda left, right: left != right,
        "<": lambda left, right: left is not None and right is not None and left < right,
        "<=": lambda left, right: left is not None and right is not None and left <= right,
        ">": lambda left, right: left is not None and right is not None and left > right,
        ">=": lambda left, right: left is not None and right is not None and left >= right,
        "in": lambda left, right: left in right if right is not None else False,
        "contains": lambda left, right: right in left if left is not None else False,
    }
    predicate = operators.get(op)
    if predicate is None:
        raise ValueError(f"Unsupported operator: {op}")
    return [obj for obj in objects if predicate(obj.get(prop, as_of=as_of), value)]


def _sort_key(value: object) -> tuple[bool, str, object]:
    return (value is None, type(value).__name__, value if value is not None else "")


__all__ = ["execute_query"]
