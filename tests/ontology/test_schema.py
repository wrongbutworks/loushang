"""Versioned ontology schema compiler contracts."""

from __future__ import annotations

import json

import pytest

from loushang.ontology.schema import (
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    SchemaCompilationError,
    SchemaVersion,
    ValueType,
)


def _project_draft(*, default: object = None) -> OntologyPackageDraft:
    return OntologyPackageDraft(
        package_id="example.project",
        namespace="urn:example:project",
        version=SchemaVersion("1.0.0"),
        object_types=[
            ObjectTypeDefinition(
                name="Project",
                semantic_id="project",
                properties=[
                    PropertyDefinition(
                        name="name",
                        value_type=ValueType.STRING,
                        semantic_id="project.name",
                        required=True,
                        default=default,
                    )
                ],
            ),
            ObjectTypeDefinition(name="Task", semantic_id="task"),
        ],
        link_types=[
            LinkTypeDefinition(
                name="contains",
                source_type="Project",
                target_type="Task",
                semantic_id="project.contains_task",
                cardinality="one_to_many",
            )
        ],
    )


def test_compiler_emits_deterministic_strict_json_and_round_trips() -> None:
    compiler = OntologyCompiler()
    compiled = compiler.compile(_project_draft())

    assert compiled.to_json() == compiler.compile(_project_draft()).to_json()
    assert compiler.load_json(compiled.to_json()) == compiled
    assert compiled.object_type("Project") is not None
    assert compiled.object_type_by_id("project").name == "Project"  # type: ignore[union-attr]
    assert compiled.object_type("Project").property_by_id("project.name") is not None  # type: ignore[union-attr]
    assert compiled.link_type("contains") is not None
    assert compiled.link_type_by_id("project.contains_task") is not None
    assert compiled.format == "loushang.ontology.schema/v2"


def test_compiled_schema_does_not_share_mutable_default_values() -> None:
    default = {"labels": ["planned"]}
    compiled = OntologyCompiler().compile(_project_draft(default=default))

    default["labels"].append("changed")

    project = compiled.object_type("Project")
    assert project is not None
    assert project.properties[0].default == {"labels": ["planned"]}

    exposed_default = project.properties[0].default
    assert isinstance(exposed_default, dict)
    exposed_default["labels"] = []
    assert project.properties[0].default == {"labels": ["planned"]}


def test_compiler_reports_all_structural_errors_with_stable_codes() -> None:
    draft = OntologyPackageDraft(
        package_id="invalid package",
        namespace="urn:example:invalid",
        version="1.0.0",
        object_types=[
            ObjectTypeDefinition(
                name="Bad Type",
                semantic_id="bad-type",
                properties=[
                    PropertyDefinition("payload", "blob", semantic_id="payload"),
                    PropertyDefinition(
                        "payload",
                        ValueType.JSON,
                        semantic_id="payload-copy",
                    ),
                ],
            ),
            ObjectTypeDefinition(name="Bad Type", semantic_id="bad-type-copy"),
        ],
        link_types=[
            LinkTypeDefinition(
                name="broken",
                source_type="Missing",
                target_type="Bad Type",
                semantic_id="broken",
                cardinality="sometimes",
            )
        ],
    )

    with pytest.raises(SchemaCompilationError) as captured:
        OntologyCompiler().compile(draft)

    codes = {diagnostic.code for diagnostic in captured.value.diagnostics}
    assert {
        "duplicate_object_type",
        "duplicate_property",
        "invalid_cardinality",
        "invalid_identifier",
        "unknown_link_endpoint",
        "unsupported_value_type",
    } <= codes


def test_compiler_rejects_parent_type_cycles() -> None:
    draft = OntologyPackageDraft(
        package_id="test.parent-cycle",
        namespace="urn:test:parent-cycle",
        version="1.0.0",
        object_types=[
            ObjectTypeDefinition(name="A", semantic_id="a", parent_types=["B"]),
            ObjectTypeDefinition(name="B", semantic_id="b", parent_types=["A"]),
        ],
    )

    with pytest.raises(SchemaCompilationError) as captured:
        OntologyCompiler().compile(draft)

    assert [item.code for item in captured.value.diagnostics] == [
        "parent_type_cycle"
    ]


def test_compiler_requires_unique_package_local_semantic_ids() -> None:
    draft = OntologyPackageDraft(
        package_id="test.semantic-ids",
        namespace="urn:test:semantic-ids",
        version="1.0.0",
        object_types=[
            ObjectTypeDefinition(
                "Asset",
                semantic_id="shared",
                properties=[
                    PropertyDefinition(
                        "code",
                        ValueType.STRING,
                        semantic_id="shared",
                    )
                ],
            ),
            ObjectTypeDefinition("MissingId"),
        ],
    )

    diagnostics = OntologyCompiler().validate(draft)

    assert [(item.code, item.path) for item in diagnostics] == [
        ("duplicate_semantic_id", "$.object_types[0].properties[0].semantic_id"),
        ("invalid_semantic_id", "$.object_types[1].semantic_id"),
    ]


def test_schema_v1_documents_are_not_loaded_as_v2() -> None:
    compiler = OntologyCompiler()
    payload = json.loads(compiler.compile(_project_draft()).to_json())
    payload["format"] = "loushang.ontology.schema/v1"

    with pytest.raises(SchemaCompilationError, match="schema/v2"):
        compiler.load_json(json.dumps(payload))
