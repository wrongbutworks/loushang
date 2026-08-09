"""Public ontology semantic-schema contracts."""

from loushang.ontology.schema.compiler import (
    SCHEMA_FORMAT,
    CompiledInterfaceTypeDefinition,
    CompiledLinkTypeDefinition,
    CompiledObjectTypeDefinition,
    CompiledOntologySchema,
    CompiledPropertyDefinition,
    OntologyCompiler,
)
from loushang.ontology.schema.definitions import (
    InterfaceTypeDefinition,
    LinkCardinality,
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyPackageDraft,
    PropertyDefinition,
    SchemaVersion,
    ValueType,
)
from loushang.ontology.schema.diagnostics import (
    SchemaCompilationError,
    SchemaDiagnostic,
)
from loushang.ontology.schema.evolution import (
    SCHEMA_DIFF_FORMAT,
    ChangeImpact,
    SchemaChange,
    SchemaDiff,
    SchemaLineageError,
    compare_schemas,
)

__all__ = [
    "SCHEMA_FORMAT",
    "SCHEMA_DIFF_FORMAT",
    "CompiledInterfaceTypeDefinition",
    "CompiledLinkTypeDefinition",
    "CompiledObjectTypeDefinition",
    "CompiledOntologySchema",
    "CompiledPropertyDefinition",
    "ChangeImpact",
    "InterfaceTypeDefinition",
    "LinkCardinality",
    "LinkTypeDefinition",
    "ObjectTypeDefinition",
    "OntologyCompiler",
    "OntologyPackageDraft",
    "PropertyDefinition",
    "SchemaCompilationError",
    "SchemaChange",
    "SchemaDiagnostic",
    "SchemaDiff",
    "SchemaLineageError",
    "SchemaVersion",
    "ValueType",
    "compare_schemas",
]
