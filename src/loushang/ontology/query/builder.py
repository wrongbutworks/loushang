"""Typed chain builder over a read-only ontology projection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from loushang.ontology.core.store_port import OntologyReadStore
from loushang.ontology.query.contracts import (
    AsOf,
    Limit,
    ObjectTypeFilter,
    Offset,
    PropertyFilter,
    QueryRequest,
    QueryResult,
    QueryStep,
    SortBy,
    StartAll,
    StartFromIds,
    StartFromType,
    Traverse,
)
from loushang.ontology.query.engine import execute_query

if TYPE_CHECKING:
    from loushang.ontology.core.object import OntologyObject


class QueryBuilder:
    """Build one immutable request and evaluate it against a projection view."""

    def __init__(self, store: OntologyReadStore) -> None:
        self._store = store
        self._steps: list[QueryStep] = []

    def start_from(self, obj: OntologyObject | UUID) -> QueryBuilder:
        from loushang.ontology.core.object import OntologyObject

        obj_id = obj.id if isinstance(obj, OntologyObject) else obj
        self._steps.append(StartFromIds((obj_id,)))
        return self

    def start_from_type(self, object_type: str) -> QueryBuilder:
        self._steps.append(StartFromType(object_type))
        return self

    def start_all(self) -> QueryBuilder:
        self._steps.append(StartAll())
        return self

    def follow(self, link_type: str, direction: str = "outgoing") -> QueryBuilder:
        self._steps.append(Traverse(link_type, direction))
        return self

    def where(self, property_name: str, op: str, value: Any) -> QueryBuilder:
        self._steps.append(PropertyFilter(property_name, op, value))
        return self

    def where_type(self, object_type: str) -> QueryBuilder:
        self._steps.append(ObjectTypeFilter(object_type))
        return self

    def limit(self, n: int) -> QueryBuilder:
        self._steps.append(Limit(n))
        return self

    def offset(self, n: int) -> QueryBuilder:
        self._steps.append(Offset(n))
        return self

    def sort_by(self, property_name: str, ascending: bool = True) -> QueryBuilder:
        self._steps.append(SortBy(property_name, ascending))
        return self

    def as_of(self, timestamp: float) -> QueryBuilder:
        self._steps.append(AsOf(timestamp))
        return self

    def to_request(self) -> QueryRequest:
        schema_version = (
            str(self._store.schema.version) if self._store.schema is not None else None
        )
        return QueryRequest(steps=self._steps, schema_version=schema_version)

    def execute_result(self) -> QueryResult:
        return execute_query(self._store, self.to_request())

    def execute(self) -> list[OntologyObject]:
        return [
            obj
            for object_id in self.execute_result().object_ids
            if (obj := self._store.get(object_id)) is not None
        ]

    def execute_ids(self) -> list[UUID]:
        return list(self.execute_result().object_ids)

    def execute_first(self) -> OntologyObject | None:
        results = self.execute()
        return results[0] if results else None

    def execute_count(self) -> int:
        return len(self.execute_result().object_ids)

    def execute_exists(self) -> bool:
        return bool(self.execute_result().object_ids)


__all__ = ["QueryBuilder"]
