"""Deterministic, language-extensible architecture analysis for Coding."""

from loushang.coding.arch.cache import (
    IMPORT_FACT_CACHE_SCHEMA_VERSION,
    ImportFactCache,
    default_import_fact_cache_path,
)
from loushang.coding.arch.import_graph import (
    IMPORT_GRAPH_SCHEMA_VERSION,
    ImportGraphAnalyzer,
    analyze_import_graph,
    query_import_graph,
)
from loushang.coding.arch.model import (
    ArchitectureDiagnostic,
    BoundaryRule,
    ImportCacheStats,
    ImportCategory,
    ImportDependencyFact,
    ImportGranularity,
    ImportGraph,
    ImportGraphEdge,
    ImportGraphNode,
    ImportGraphQuery,
    ImportKind,
    ImportModuleFact,
    ImportProviderScan,
    ImportSelection,
    SourceEvidence,
)
from loushang.coding.arch.providers import (
    PYTHON_IMPORT_PROVIDER_VERSION,
    ImportGraphProvider,
    PythonImportGraphProvider,
)

__all__ = [
    "IMPORT_GRAPH_SCHEMA_VERSION",
    "IMPORT_FACT_CACHE_SCHEMA_VERSION",
    "PYTHON_IMPORT_PROVIDER_VERSION",
    "ArchitectureDiagnostic",
    "BoundaryRule",
    "ImportCategory",
    "ImportCacheStats",
    "ImportDependencyFact",
    "ImportGranularity",
    "ImportGraph",
    "ImportGraphAnalyzer",
    "ImportGraphEdge",
    "ImportGraphNode",
    "ImportGraphProvider",
    "ImportGraphQuery",
    "ImportKind",
    "ImportModuleFact",
    "ImportProviderScan",
    "ImportFactCache",
    "ImportSelection",
    "PythonImportGraphProvider",
    "SourceEvidence",
    "analyze_import_graph",
    "default_import_fact_cache_path",
    "query_import_graph",
]
