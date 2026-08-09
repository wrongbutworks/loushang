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
    ProjectionFreshness,
    ProjectionFreshnessStatus,
    ProjectionSnapshot,
    ProjectionState,
    evaluate_projection_freshness,
)
from loushang.ontology.projection.ports import (
    ProjectionReadStore,
    ProjectionStore,
    ProjectionUnavailableError,
)

__all__ = [
    "ProjectedLink",
    "ProjectedObject",
    "ProjectedProperty",
    "ProjectionDiagnostic",
    "ProjectionFreshness",
    "ProjectionFreshnessStatus",
    "ProjectionMaterializationError",
    "ProjectionReadStore",
    "ProjectionSnapshot",
    "ProjectionState",
    "ProjectionStore",
    "ProjectionUnavailableError",
    "evaluate_projection_freshness",
    "materialize_projection",
]
