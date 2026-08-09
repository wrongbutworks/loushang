"""Immutable ontology projection models, ports, and materialization."""

from loushang.ontology.projection.materializer import (
    ProjectionDiagnostic,
    ProjectionMaterializationError,
    materialize_projection,
)
from loushang.ontology.projection.model import (
    ProjectedLink,
    ProjectedObject,
    ProjectedProperty,
    ProjectionSnapshot,
    ProjectionState,
)
from loushang.ontology.projection.ports import (
    ProjectionReadStore,
    ProjectionStaleError,
    ProjectionStore,
    ProjectionUnavailableError,
)

__all__ = [
    "ProjectedLink",
    "ProjectedObject",
    "ProjectedProperty",
    "ProjectionDiagnostic",
    "ProjectionMaterializationError",
    "ProjectionReadStore",
    "ProjectionSnapshot",
    "ProjectionStaleError",
    "ProjectionState",
    "ProjectionStore",
    "ProjectionUnavailableError",
    "materialize_projection",
]
