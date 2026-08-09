"""Structural storage ports used by the ontology facade and query engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from loushang.ontology.core.projection import ProjectionState, StoreMutation

if TYPE_CHECKING:
    from loushang.ontology.core.constraints import IntegrityViolation
    from loushang.ontology.core.link_type import LinkType
    from loushang.ontology.core.object import OntologyObject
    from loushang.ontology.core.object_type import ObjectType
    from loushang.ontology.core.schema_runtime import PropertyValidators
    from loushang.ontology.schema import CompiledOntologySchema


class OntologyReadStore(Protocol):
    """Read surface required by the reference query evaluator."""

    @property
    def schema(self) -> CompiledOntologySchema | None: ...

    @property
    def projection_state(self) -> ProjectionState: ...

    def get(self, obj_id: UUID) -> OntologyObject | None: ...

    def get_by_type(self, object_type: str) -> list[OntologyObject]: ...

    def find_neighbors(
        self,
        obj_id: UUID,
        link_type: str,
        direction: str = "outgoing",
        as_of: float | None = None,
        active_only: bool = True,
    ) -> list[OntologyObject]: ...

    def all_objects(self) -> list[OntologyObject]: ...


class OperationalMutationStore(Protocol):
    """Read side of the operational recovery journal (not semantic Facts)."""

    @property
    def current_watermark(self) -> int: ...

    def read_mutations(self, *, after_sequence: int = 0) -> tuple[StoreMutation, ...]: ...


class ProjectionStore(Protocol):
    """Freshness and deterministic rebuild contract for serving projections."""

    @property
    def projection_state(self) -> ProjectionState: ...

    def rebuild_projections(self) -> ProjectionState: ...


class OntologyStore(
    OntologyReadStore,
    OperationalMutationStore,
    ProjectionStore,
    Protocol,
):
    """Minimal authority, journal, and projection contract for Wave 1."""

    def bind_schema(
        self,
        schema: CompiledOntologySchema,
        *,
        property_validators: PropertyValidators | None = None,
    ) -> None: ...

    def create(
        self,
        object_type: str,
        properties: dict[str, Any] | None = None,
        obj_id: UUID | None = None,
    ) -> OntologyObject: ...

    def get_object_type(self, name: str) -> ObjectType | None: ...

    def get_link_type(self, name: str) -> LinkType | None: ...

    def delete(self, obj_id: UUID) -> bool: ...

    def set_property(
        self,
        obj: OntologyObject,
        name: str,
        value: Any,
        *,
        timestamp: float | None = None,
        author: str | None = None,
        source: str | None = None,
    ) -> None: ...

    def link_objects(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        *,
        timestamp: float | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None: ...

    def unlink_objects(
        self,
        source: OntologyObject,
        link_type: str,
        target: OntologyObject,
        *,
        timestamp: float | None = None,
    ) -> None: ...

    def find_by_property(
        self,
        property_name: str,
        value: Any,
        object_type: str | None = None,
    ) -> list[OntologyObject]: ...

    def count(self) -> int: ...

    def validate_integrity(self) -> tuple[IntegrityViolation, ...]: ...

__all__ = [
    "OntologyReadStore",
    "OntologyStore",
    "OperationalMutationStore",
    "ProjectionStore",
]
