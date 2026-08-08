"""Public ontology semantic-schema contracts."""

from loushang.ontology.schema.compiler import (
    SCHEMA_FORMAT,
    CompiledLinkTypeDefinition,
    CompiledObjectTypeDefinition,
    CompiledOntologySchema,
    CompiledPropertyDefinition,
    OntologyCompiler,
)
from loushang.ontology.schema.definitions import (
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

__all__ = [
    "SCHEMA_FORMAT",
    "CompiledLinkTypeDefinition",
    "CompiledObjectTypeDefinition",
    "CompiledOntologySchema",
    "CompiledPropertyDefinition",
    "LinkCardinality",
    "LinkTypeDefinition",
    "ObjectTypeDefinition",
    "OntologyCompiler",
    "OntologyPackageDraft",
    "PropertyDefinition",
    "SchemaCompilationError",
    "SchemaDiagnostic",
    "SchemaVersion",
    "ValueType",
]
