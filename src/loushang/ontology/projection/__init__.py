"""Immutable ontology projection models, ports, and materialization."""

from loushang.ontology.projection.materializer import (
    ProjectionDiagnostic,
    ProjectionMaterializationError,
    materialize_projection,
)
from loushang.ontology.projection.model import (
    FactOrigin,
    MaterializationCut,
    OperationalOrigin,
    ProjectedLink,
    ProjectedObject,
    ProjectedProperty,
    ProjectionFreshness,
    ProjectionFreshnessStatus,
    ProjectionSnapshot,
    ProjectionState,
    SchemaDefaultOrigin,
    SourceOrigin,
    ValueOrigin,
    evaluate_projection_freshness,
)
from loushang.ontology.projection.ports import (
    ProjectionReadStore,
    ProjectionStore,
    ProjectionUnavailableError,
)

__all__ = [
    "FactOrigin",
    "MaterializationCut",
    "OperationalOrigin",
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
    "SchemaDefaultOrigin",
    "SourceOrigin",
    "ValueOrigin",
    "evaluate_projection_freshness",
    "materialize_projection",
]
