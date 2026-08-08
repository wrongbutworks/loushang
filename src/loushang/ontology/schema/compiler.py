"""Pure compiler for versioned ontology schema drafts."""

from __future__ import annotations

import json as stdlib_json
import re
from dataclasses import dataclass, field
from typing import cast

from loushang.foundation.json import (
    JSONValue,
    JsonValueError,
    dump_json_value,
    require_json_mapping,
    require_json_value,
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

SCHEMA_FORMAT = "loushang.ontology.schema/v1"

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9.-]+)?$")


@dataclass(frozen=True, slots=True)
class CompiledPropertyDefinition:
    """Validated property definition with an isolated JSON default value."""

    name: str
    value_type: ValueType
    required: bool
    unique: bool
    indexed: bool
    description: str
    _default_json: str = field(repr=False)

    @property
    def default(self) -> JSONValue:
        # Return a fresh JSON tree so callers cannot mutate the snapshot.
        return cast(JSONValue, stdlib_json.loads(self._default_json))


@dataclass(frozen=True, slots=True)
class CompiledObjectTypeDefinition:
    """Validated, immutable object-type definition."""

    name: str
    properties: tuple[CompiledPropertyDefinition, ...]
    parent_types: tuple[str, ...]
    abstract: bool
    icon: str | None
    description: str
    display_name_property: str | None

    def property(self, name: str) -> CompiledPropertyDefinition | None:
        return next((item for item in self.properties if item.name == name), None)


@dataclass(frozen=True, slots=True)
class CompiledLinkTypeDefinition:
    """Validated, immutable link-type definition."""

    name: str
    source_type: str
    target_type: str
    cardinality: LinkCardinality
    required: bool
    inverse_name: str | None
    temporal: bool
    description: str


@dataclass(frozen=True, slots=True)
class CompiledOntologySchema:
    """Validated immutable schema snapshot consumed by runtimes."""

    package_id: str
    namespace: str
    version: SchemaVersion
    object_types: tuple[CompiledObjectTypeDefinition, ...]
    link_types: tuple[CompiledLinkTypeDefinition, ...]
    format: str = SCHEMA_FORMAT

    def object_type(self, name: str) -> CompiledObjectTypeDefinition | None:
        return next((item for item in self.object_types if item.name == name), None)

    def link_type(self, name: str) -> CompiledLinkTypeDefinition | None:
        return next((item for item in self.link_types if item.name == name), None)

    def to_dict(self) -> dict[str, JSONValue]:
        """Project the snapshot to its stable strict-JSON representation."""

        return {
            "format": self.format,
            "package_id": self.package_id,
            "namespace": self.namespace,
            "version": self.version.value,
            "object_types": [
                {
                    "name": object_type.name,
                    "properties": [
                        {
                            "name": prop.name,
                            "value_type": prop.value_type.value,
                            "required": prop.required,
                            "unique": prop.unique,
                            "indexed": prop.indexed,
                            "default": prop.default,
                            "description": prop.description,
                        }
                        for prop in object_type.properties
                    ],
                    "parent_types": list(object_type.parent_types),
                    "abstract": object_type.abstract,
                    "icon": object_type.icon,
                    "description": object_type.description,
                    "display_name_property": object_type.display_name_property,
                }
                for object_type in self.object_types
            ],
            "link_types": [
                {
                    "name": link_type.name,
                    "source_type": link_type.source_type,
                    "target_type": link_type.target_type,
                    "cardinality": link_type.cardinality.value,
                    "required": link_type.required,
                    "inverse_name": link_type.inverse_name,
                    "temporal": link_type.temporal,
                    "description": link_type.description,
                }
                for link_type in self.link_types
            ],
        }

    def to_json(self) -> str:
        """Serialize to canonical compact JSON."""

        return dump_json_value(self.to_dict(), name="compiled ontology schema", sort_keys=True)


class OntologyCompiler:
    """Validate a draft and return a detached schema snapshot.

    The compiler has no registry, store, filesystem, network, or process side
    effects. A single instance is safe to reuse because it owns no state.
    """

    def validate(self, draft: OntologyPackageDraft) -> tuple[SchemaDiagnostic, ...]:
        """Return deterministic diagnostics without producing a snapshot."""

        _, diagnostics = self._compile(draft)
        return diagnostics

    def compile(self, draft: OntologyPackageDraft) -> CompiledOntologySchema:
        """Compile ``draft`` or raise all discovered structural diagnostics."""

        compiled, diagnostics = self._compile(draft)
        if diagnostics:
            raise SchemaCompilationError(diagnostics)
        assert compiled is not None
        return compiled

    def load_json(self, payload: str) -> CompiledOntologySchema:
        """Load canonical schema JSON through the same validation boundary."""

        try:
            raw = stdlib_json.loads(payload)
            document = require_json_mapping(raw, name="ontology schema")
            draft = _draft_from_document(document)
        except (JsonValueError, KeyError, TypeError, ValueError, stdlib_json.JSONDecodeError) as exc:
            raise SchemaCompilationError(
                (
                    SchemaDiagnostic(
                        code="invalid_schema_document",
                        path="$",
                        message=str(exc),
                    ),
                )
            ) from exc
        return self.compile(draft)

    def _compile(
        self,
        draft: OntologyPackageDraft,
    ) -> tuple[CompiledOntologySchema | None, tuple[SchemaDiagnostic, ...]]:
        diagnostics: list[SchemaDiagnostic] = []

        _validate_identifier(draft.package_id, "$.package_id", diagnostics)
        if not isinstance(draft.namespace, str) or not draft.namespace.strip():
            diagnostics.append(
                SchemaDiagnostic("invalid_namespace", "$.namespace", "namespace must be a non-empty string")
            )

        version = draft.version
        if not isinstance(version, SchemaVersion) or not _VERSION.fullmatch(version.value):
            diagnostics.append(
                SchemaDiagnostic(
                    "invalid_schema_version",
                    "$.version",
                    "version must contain one to three numeric components",
                )
            )

        compiled_objects: list[CompiledObjectTypeDefinition] = []
        object_names: set[str] = set()
        for object_index, object_type in enumerate(draft.object_types):
            object_path = f"$.object_types[{object_index}]"
            _validate_identifier(object_type.name, f"{object_path}.name", diagnostics)
            if object_type.name in object_names:
                diagnostics.append(
                    SchemaDiagnostic(
                        "duplicate_object_type",
                        f"{object_path}.name",
                        f"object type '{object_type.name}' is declared more than once",
                    )
                )
            object_names.add(object_type.name)

            compiled_properties: list[CompiledPropertyDefinition] = []
            property_names: set[str] = set()
            for property_index, prop in enumerate(object_type.properties):
                property_path = f"{object_path}.properties[{property_index}]"
                _validate_identifier(prop.name, f"{property_path}.name", diagnostics)
                if prop.name in property_names:
                    diagnostics.append(
                        SchemaDiagnostic(
                            "duplicate_property",
                            f"{property_path}.name",
                            f"property '{prop.name}' is declared more than once",
                        )
                    )
                property_names.add(prop.name)

                value_type = _normalize_value_type(prop.value_type)
                if value_type is None:
                    diagnostics.append(
                        SchemaDiagnostic(
                            "unsupported_value_type",
                            f"{property_path}.value_type",
                            f"unsupported value type '{_value_label(prop.value_type)}'",
                        )
                    )

                default_json: str | None = None
                try:
                    default_value = require_json_value(prop.default, name=f"{property_path}.default")
                    default_json = dump_json_value(default_value, sort_keys=True)
                except JsonValueError as exc:
                    diagnostics.append(
                        SchemaDiagnostic("invalid_default", f"{property_path}.default", str(exc))
                    )

                if value_type is not None and default_json is not None:
                    compiled_properties.append(
                        CompiledPropertyDefinition(
                            name=prop.name,
                            value_type=value_type,
                            required=prop.required,
                            unique=prop.unique,
                            indexed=prop.indexed,
                            description=prop.description,
                            _default_json=default_json,
                        )
                    )

            compiled_objects.append(
                CompiledObjectTypeDefinition(
                    name=object_type.name,
                    properties=tuple(compiled_properties),
                    parent_types=tuple(object_type.parent_types),
                    abstract=object_type.abstract,
                    icon=object_type.icon,
                    description=object_type.description,
                    display_name_property=object_type.display_name_property,
                )
            )

        for object_index, object_type in enumerate(draft.object_types):
            for parent_index, parent_name in enumerate(object_type.parent_types):
                if parent_name not in object_names:
                    diagnostics.append(
                        SchemaDiagnostic(
                            "unknown_parent_type",
                            f"$.object_types[{object_index}].parent_types[{parent_index}]",
                            f"parent object type '{parent_name}' is not declared",
                        )
                    )

        compiled_links: list[CompiledLinkTypeDefinition] = []
        link_names: set[str] = set()
        for link_index, link_type in enumerate(draft.link_types):
            link_path = f"$.link_types[{link_index}]"
            _validate_identifier(link_type.name, f"{link_path}.name", diagnostics)
            if link_type.name in link_names:
                diagnostics.append(
                    SchemaDiagnostic(
                        "duplicate_link_type",
                        f"{link_path}.name",
                        f"link type '{link_type.name}' is declared more than once",
                    )
                )
            link_names.add(link_type.name)

            for endpoint, endpoint_name in (
                ("source_type", link_type.source_type),
                ("target_type", link_type.target_type),
            ):
                if endpoint_name not in object_names:
                    diagnostics.append(
                        SchemaDiagnostic(
                            "unknown_link_endpoint",
                            f"{link_path}.{endpoint}",
                            f"object type '{endpoint_name}' is not declared",
                        )
                    )

            cardinality = _normalize_cardinality(link_type.cardinality)
            if cardinality is None:
                diagnostics.append(
                    SchemaDiagnostic(
                        "invalid_cardinality",
                        f"{link_path}.cardinality",
                        f"unsupported cardinality '{_value_label(link_type.cardinality)}'",
                    )
                )
            else:
                compiled_links.append(
                    CompiledLinkTypeDefinition(
                        name=link_type.name,
                        source_type=link_type.source_type,
                        target_type=link_type.target_type,
                        cardinality=cardinality,
                        required=link_type.required,
                        inverse_name=link_type.inverse_name,
                        temporal=link_type.temporal,
                        description=link_type.description,
                    )
                )

        if diagnostics:
            return None, tuple(diagnostics)

        assert isinstance(version, SchemaVersion)
        return (
            CompiledOntologySchema(
                package_id=draft.package_id,
                namespace=draft.namespace,
                version=version,
                object_types=tuple(sorted(compiled_objects, key=lambda item: item.name)),
                link_types=tuple(sorted(compiled_links, key=lambda item: item.name)),
            ),
            (),
        )


def _validate_identifier(
    value: object,
    path: str,
    diagnostics: list[SchemaDiagnostic],
) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        diagnostics.append(
            SchemaDiagnostic(
                "invalid_identifier",
                path,
                "identifier must start with a letter and contain only letters, digits, '.', '_' or '-'",
            )
        )


def _normalize_value_type(value: object) -> ValueType | None:
    if isinstance(value, ValueType):
        return value
    if isinstance(value, str):
        try:
            return ValueType(value)
        except ValueError:
            return None
    return None


def _normalize_cardinality(value: object) -> LinkCardinality | None:
    if isinstance(value, LinkCardinality):
        return value
    if isinstance(value, str):
        try:
            return LinkCardinality(value)
        except ValueError:
            return None
    return None


def _value_label(value: object) -> str:
    if isinstance(value, type):
        return value.__name__
    return str(value)


def _draft_from_document(document: dict[str, JSONValue]) -> OntologyPackageDraft:
    if document.get("format") != SCHEMA_FORMAT:
        raise ValueError(f"format must be '{SCHEMA_FORMAT}'")

    object_values = _require_list(document, "object_types")
    link_values = _require_list(document, "link_types")
    object_types = [_object_from_value(value) for value in object_values]
    link_types = [_link_from_value(value) for value in link_values]

    return OntologyPackageDraft(
        package_id=_require_string(document, "package_id"),
        namespace=_require_string(document, "namespace"),
        version=_require_string(document, "version"),
        object_types=object_types,
        link_types=link_types,
    )


def _object_from_value(value: JSONValue) -> ObjectTypeDefinition:
    document = require_json_mapping(value, name="object type")
    properties = [_property_from_value(item) for item in _require_list(document, "properties")]
    parents = _require_list(document, "parent_types")
    if not all(isinstance(item, str) for item in parents):
        raise TypeError("parent_types must contain only strings")
    return ObjectTypeDefinition(
        name=_require_string(document, "name"),
        properties=properties,
        parent_types=cast(list[str], parents),
        abstract=_require_bool(document, "abstract"),
        icon=_require_optional_string(document, "icon"),
        description=_require_string(document, "description"),
        display_name_property=_require_optional_string(document, "display_name_property"),
    )


def _property_from_value(value: JSONValue) -> PropertyDefinition:
    document = require_json_mapping(value, name="property")
    return PropertyDefinition(
        name=_require_string(document, "name"),
        value_type=_require_string(document, "value_type"),
        required=_require_bool(document, "required"),
        unique=_require_bool(document, "unique"),
        indexed=_require_bool(document, "indexed"),
        default=document["default"],
        description=_require_string(document, "description"),
    )


def _link_from_value(value: JSONValue) -> LinkTypeDefinition:
    document = require_json_mapping(value, name="link type")
    return LinkTypeDefinition(
        name=_require_string(document, "name"),
        source_type=_require_string(document, "source_type"),
        target_type=_require_string(document, "target_type"),
        cardinality=_require_string(document, "cardinality"),
        required=_require_bool(document, "required"),
        inverse_name=_require_optional_string(document, "inverse_name"),
        temporal=_require_bool(document, "temporal"),
        description=_require_string(document, "description"),
    )


def _require_list(document: dict[str, JSONValue], key: str) -> list[JSONValue]:
    value = document[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be an array")
    return value


def _require_string(document: dict[str, JSONValue], key: str) -> str:
    value = document[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _require_optional_string(document: dict[str, JSONValue], key: str) -> str | None:
    value = document[key]
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{key} must be a string or null")
    return value


def _require_bool(document: dict[str, JSONValue], key: str) -> bool:
    value = document[key]
    if type(value) is not bool:
        raise TypeError(f"{key} must be a boolean")
    return cast(bool, value)


__all__ = [
    "CompiledLinkTypeDefinition",
    "CompiledObjectTypeDefinition",
    "CompiledOntologySchema",
    "CompiledPropertyDefinition",
    "OntologyCompiler",
    "SCHEMA_FORMAT",
]
