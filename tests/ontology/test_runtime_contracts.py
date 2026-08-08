"""Runtime enforcement promised by the Semantic Kernel V1 schema."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from loushang.ontology import Cardinality, Ontology, OntologyObject
from loushang.ontology.schema import (
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    SchemaCompilationError,
    ValueType,
)


def _runtime_from_draft(draft: OntologyPackageDraft) -> Ontology:
    payload = OntologyCompiler().compile(draft).to_json()
    return Ontology.from_schema_json(payload)


def _values_draft() -> OntologyPackageDraft:
    return OntologyPackageDraft(
        package_id="test.values",
        namespace="urn:test:values",
        version="1.0.0",
        object_types=[
            ObjectTypeDefinition(
                name="Values",
                properties=[
                    PropertyDefinition("text", ValueType.STRING),
                    PropertyDefinition("count", ValueType.INTEGER),
                    PropertyDefinition("ratio", ValueType.NUMBER),
                    PropertyDefinition("enabled", ValueType.BOOLEAN),
                    PropertyDefinition("observed_at", ValueType.DATETIME),
                    PropertyDefinition("payload", ValueType.JSON),
                ],
            )
        ],
    )


def test_loaded_schema_enforces_supported_value_types_on_create() -> None:
    ontology = _runtime_from_draft(_values_draft())
    observed_at = datetime(2026, 8, 8, tzinfo=UTC)

    created = ontology.create(
        "Values",
        text="ready",
        count=3,
        ratio=2.5,
        enabled=True,
        observed_at=observed_at,
        payload={"labels": ["a", "b"]},
    )

    assert created.get("observed_at") == observed_at


@pytest.mark.parametrize(
    ("property_name", "invalid_value"),
    [
        ("text", 1),
        ("count", True),
        ("ratio", "2.5"),
        ("ratio", float("nan")),
        ("enabled", 1),
        ("observed_at", "2026-08-08T00:00:00Z"),
        ("payload", ("not", "json")),
    ],
)
def test_loaded_schema_rejects_invalid_value_types(
    property_name: str,
    invalid_value: object,
) -> None:
    ontology = _runtime_from_draft(_values_draft())

    with pytest.raises(ValueError, match=property_name):
        ontology.create("Values", **{property_name: invalid_value})


def test_number_accepts_json_integer_but_not_boolean() -> None:
    ontology = _runtime_from_draft(_values_draft())

    assert ontology.create("Values", ratio=2).get("ratio") == 2
    with pytest.raises(ValueError, match="ratio"):
        ontology.create("Values", ratio=False)


def test_abstract_object_type_cannot_be_instantiated() -> None:
    ontology = _runtime_from_draft(
        OntologyPackageDraft(
            package_id="test.abstract",
            namespace="urn:test:abstract",
            version="1.0.0",
            object_types=[ObjectTypeDefinition(name="Resource", abstract=True)],
        )
    )

    with pytest.raises(ValueError, match="abstract"):
        ontology.create("Resource")


def test_inherited_properties_are_required_validated_and_indexed() -> None:
    ontology = _runtime_from_draft(
        OntologyPackageDraft(
            package_id="test.inheritance",
            namespace="urn:test:inheritance",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    name="Resource",
                    properties=[
                        PropertyDefinition(
                            "code",
                            ValueType.STRING,
                            required=True,
                            indexed=True,
                        )
                    ],
                ),
                ObjectTypeDefinition(
                    name="Project",
                    parent_types=["Resource"],
                    properties=[PropertyDefinition("budget", ValueType.NUMBER)],
                ),
            ],
        )
    )

    with pytest.raises(ValueError, match="code"):
        ontology.create("Project", budget=10)
    with pytest.raises(ValueError, match="code"):
        ontology.create("Project", code=100, budget=10)

    project = ontology.create("Project", code="P-1", budget=10)
    assert ontology.find_by_property("code", "P-1", "Project") == [project]


def test_compiler_rejects_parent_type_cycles() -> None:
    draft = OntologyPackageDraft(
        package_id="test.parent-cycle",
        namespace="urn:test:parent-cycle",
        version="1.0.0",
        object_types=[
            ObjectTypeDefinition(name="A", parent_types=["B"]),
            ObjectTypeDefinition(name="B", parent_types=["A"]),
        ],
    )

    with pytest.raises(SchemaCompilationError) as captured:
        OntologyCompiler().compile(draft)

    assert [item.code for item in captured.value.diagnostics] == [
        "parent_type_cycle"
    ]


def _cardinality_runtime(
    cardinality: Cardinality,
) -> tuple[Ontology, list[OntologyObject]]:
    ontology = _runtime_from_draft(
        OntologyPackageDraft(
            package_id="test.cardinality",
            namespace="urn:test:cardinality",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(name="Source"),
                ObjectTypeDefinition(name="Target"),
            ],
            link_types=[
                LinkTypeDefinition(
                    name="relates_to",
                    source_type="Source",
                    target_type="Target",
                    cardinality=cardinality.name.lower(),
                )
            ],
        )
    )
    objects = [
        ontology.create("Source"),
        ontology.create("Source"),
        ontology.create("Target"),
        ontology.create("Target"),
    ]
    return ontology, objects


@pytest.mark.parametrize(
    ("cardinality", "reject_second_target", "reject_second_source"),
    [
        (Cardinality.ONE_TO_ONE, True, True),
        (Cardinality.ONE_TO_MANY, False, True),
        (Cardinality.MANY_TO_ONE, True, False),
        (Cardinality.MANY_TO_MANY, False, False),
    ],
)
def test_link_cardinality_is_enforced(
    cardinality: Cardinality,
    reject_second_target: bool,
    reject_second_source: bool,
) -> None:
    ontology, objects = _cardinality_runtime(cardinality)
    source_1, source_2, target_1, target_2 = objects
    ontology.link(source_1, "relates_to", target_1)

    if reject_second_target:
        with pytest.raises(ValueError, match="cardinality"):
            ontology.link(source_1, "relates_to", target_2)
    else:
        ontology.link(source_1, "relates_to", target_2)

    if reject_second_source:
        with pytest.raises(ValueError, match="cardinality"):
            ontology.link(source_2, "relates_to", target_1)
    else:
        ontology.link(source_2, "relates_to", target_1)


def test_unlink_releases_cardinality_slot() -> None:
    ontology, objects = _cardinality_runtime(Cardinality.ONE_TO_ONE)
    source_1, _, target_1, target_2 = objects
    ontology.link(source_1, "relates_to", target_1)

    ontology.unlink(source_1, "relates_to", target_1)
    ontology.link(source_1, "relates_to", target_2)

    assert ontology.query().start_from(source_1).follow("relates_to").execute() == [
        target_2
    ]
