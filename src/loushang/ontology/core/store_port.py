"""Read-only structural projection port used by the query engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from loushang.ontology.core.projection import ProjectionState

if TYPE_CHECKING:
    from loushang.ontology.core.object import OntologyObject
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


__all__ = [
    "OntologyReadStore",
]
