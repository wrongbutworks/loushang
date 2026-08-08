"""Versioned ontology schema contracts and facade compatibility."""

from __future__ import annotations

import pytest

from loushang.ontology import Ontology, Property
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
                properties=[
                    PropertyDefinition(
                        name="name",
                        value_type=ValueType.STRING,
                        required=True,
                        default=default,
                    )
                ],
            ),
            ObjectTypeDefinition(name="Task"),
        ],
        link_types=[
            LinkTypeDefinition(
                name="contains",
                source_type="Project",
                target_type="Task",
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
    assert compiled.link_type("contains") is not None


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
                properties=[
                    PropertyDefinition("payload", "blob"),
                    PropertyDefinition("payload", ValueType.JSON),
                ],
            ),
            ObjectTypeDefinition(name="Bad Type"),
        ],
        link_types=[
            LinkTypeDefinition(
                name="broken",
                source_type="Missing",
                target_type="Bad Type",
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


def test_facade_freezes_and_binds_schema_before_first_object() -> None:
    ontology = Ontology(
        package_id="example.facade",
        namespace="urn:example:facade",
        schema_version="1.0.0",
    )
    ontology.define_object_type(
        "Project",
        properties=[Property("name", str, required=True, indexed=True)],
    )

    assert ontology.compiled_schema is None
    project = ontology.create("Project", name="Apollo")

    assert project.get("name") == "Apollo"
    assert ontology.compiled_schema is not None
    assert ontology.compiled_schema.package_id == "example.facade"
    assert ontology.compiled_schema.object_type("Project") is not None

    with pytest.raises(RuntimeError, match="frozen"):
        ontology.define_object_type("Task")


def test_facade_can_freeze_explicitly_and_reuses_the_snapshot() -> None:
    ontology = Ontology()
    ontology.define_object_type("Project", properties=[Property("name", str)])

    first = ontology.freeze_schema()
    second = ontology.freeze_schema()

    assert first is second
    assert ontology.compiled_schema is first


def test_facade_reports_unsupported_python_property_types_at_freeze() -> None:
    ontology = Ontology()
    ontology.define_object_type("Blob", properties=[Property("payload", bytes)])

    with pytest.raises(SchemaCompilationError) as captured:
        ontology.freeze_schema()

    assert [item.code for item in captured.value.diagnostics] == [
        "unsupported_value_type"
    ]
    assert ontology.compiled_schema is None


def test_failed_create_of_unknown_type_does_not_freeze_facade() -> None:
    ontology = Ontology()

    with pytest.raises(ValueError, match="not registered"):
        ontology.create("Missing")

    ontology.define_object_type("Missing")
    assert ontology.create("Missing").object_type == "Missing"
