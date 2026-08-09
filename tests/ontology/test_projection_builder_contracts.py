"""Validation contracts used by the internal Fact projection builder."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from loushang.ontology.core.object import OntologyObject
from loushang.ontology.core.store import ObjectStore
from loushang.ontology.schema import (
    LinkCardinality,
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    SchemaCompilationError,
    ValueType,
)


def _builder_from_draft(draft: OntologyPackageDraft) -> ObjectStore:
    store = ObjectStore()
    store.bind_schema(OntologyCompiler().compile(draft))
    return store


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


def test_builder_enforces_supported_projection_value_types() -> None:
    store = _builder_from_draft(_values_draft())
    observed_at = datetime(2026, 8, 8, tzinfo=UTC)

    created = store.create(
        "Values",
        {
            "text": "ready",
            "count": 3,
            "ratio": 2.5,
            "enabled": True,
            "observed_at": observed_at,
            "payload": {"labels": ["a", "b"]},
        },
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
def test_builder_rejects_invalid_projection_value_types(
    property_name: str,
    invalid_value: object,
) -> None:
    store = _builder_from_draft(_values_draft())

    with pytest.raises(ValueError, match=property_name):
        store.create("Values", {property_name: invalid_value})


def test_number_accepts_json_integer_but_not_boolean() -> None:
    store = _builder_from_draft(_values_draft())

    assert store.create("Values", {"ratio": 2}).get("ratio") == 2
    with pytest.raises(ValueError, match="ratio"):
        store.create("Values", {"ratio": False})


def test_abstract_object_type_cannot_be_projected() -> None:
    store = _builder_from_draft(
        OntologyPackageDraft(
            package_id="test.abstract",
            namespace="urn:test:abstract",
            version="1.0.0",
            object_types=[ObjectTypeDefinition(name="Resource", abstract=True)],
        )
    )

    with pytest.raises(ValueError, match="abstract"):
        store.create("Resource")


def test_inherited_properties_are_required_validated_and_indexed() -> None:
    store = _builder_from_draft(
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
        store.create("Project", {"budget": 10})
    with pytest.raises(ValueError, match="code"):
        store.create("Project", {"code": 100, "budget": 10})

    project = store.create("Project", {"code": "P-1", "budget": 10})
    assert store.find_by_property("code", "P-1", "Project") == [project]


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


def _cardinality_builder(
    cardinality: LinkCardinality,
) -> tuple[ObjectStore, list[OntologyObject]]:
    store = _builder_from_draft(
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
                    cardinality=cardinality,
                )
            ],
        )
    )
    objects = [
        store.create("Source"),
        store.create("Source"),
        store.create("Target"),
        store.create("Target"),
    ]
    return store, objects


@pytest.mark.parametrize(
    ("cardinality", "reject_second_target", "reject_second_source"),
    [
        (LinkCardinality.ONE_TO_ONE, True, True),
        (LinkCardinality.ONE_TO_MANY, False, True),
        (LinkCardinality.MANY_TO_ONE, True, False),
        (LinkCardinality.MANY_TO_MANY, False, False),
    ],
)
def test_link_cardinality_is_enforced_during_materialization(
    cardinality: LinkCardinality,
    reject_second_target: bool,
    reject_second_source: bool,
) -> None:
    store, objects = _cardinality_builder(cardinality)
    source_1, source_2, target_1, target_2 = objects
    store.link_objects(source_1, "relates_to", target_1)

    if reject_second_target:
        with pytest.raises(ValueError, match="cardinality"):
            store.link_objects(source_1, "relates_to", target_2)
    else:
        store.link_objects(source_1, "relates_to", target_2)

    if reject_second_source:
        with pytest.raises(ValueError, match="cardinality"):
            store.link_objects(source_2, "relates_to", target_1)
    else:
        store.link_objects(source_2, "relates_to", target_1)


def test_unlink_releases_internal_cardinality_slot() -> None:
    store, objects = _cardinality_builder(LinkCardinality.ONE_TO_ONE)
    source_1, _, target_1, target_2 = objects
    store.link_objects(source_1, "relates_to", target_1)

    store.unlink_objects(source_1, "relates_to", target_1)
    store.link_objects(source_1, "relates_to", target_2)

    assert store.find_neighbors(source_1.id, "relates_to") == [target_2]
