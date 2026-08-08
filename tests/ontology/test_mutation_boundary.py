"""Controlled mutation behavior for Store-managed ontology objects."""

from __future__ import annotations

import pytest

from loushang.ontology import Cardinality, Ontology, OntologyObject, Property
from loushang.ontology.fusion.mapper import DataFusion, FieldMapping, SourceMapping


def test_standalone_objects_keep_local_mutation_behavior() -> None:
    source = OntologyObject("Source")
    target = OntologyObject("Target")

    source.set("name", "standalone")
    source.link("relates_to", target)

    assert source.get("name") == "standalone"
    assert [link.target_id for link in source.get_links("relates_to")] == [target.id]

    source.unlink("relates_to", target)
    assert source.get_links("relates_to") == []


def test_managed_set_validates_before_history_or_index_changes() -> None:
    ontology = Ontology()
    ontology.define_object_type(
        "Item",
        properties=[
            Property("code", str, indexed=True),
            Property("score", int),
        ],
    )
    item = ontology.create("Item", code="old", score=1)
    code_history = item.history("code")

    with pytest.raises(ValueError, match="code"):
        item.set("code", 7)

    assert item.history("code") == code_history
    assert item.get("code") == "old"
    assert ontology.find_by_property("code", "old", "Item") == [item]
    assert ontology.find_by_property("code", 7, "Item") == []


def test_managed_set_updates_index_and_temporal_metadata() -> None:
    ontology = Ontology()
    ontology.define_object_type(
        "Item",
        properties=[Property("code", str, indexed=True)],
    )
    item = ontology.create("Item", code="old")

    ontology.set_property(
        item,
        "code",
        "new",
        timestamp=123.0,
        author="actor-1",
        source="manual",
    )

    assert ontology.find_by_property("code", "old", "Item") == []
    assert ontology.find_by_property("code", "new", "Item") == [item]
    latest = item.history("code")[-1]
    assert latest.value == "new"
    assert latest.timestamp == 123.0
    assert latest.author == "actor-1"
    assert latest.source == "manual"


def test_deleted_managed_object_cannot_be_mutated() -> None:
    ontology = Ontology()
    ontology.define_object_type("Item", properties=[Property("name", str)])
    item = ontology.create("Item", name="before")
    assert ontology.delete(item.id) is True

    with pytest.raises(ValueError, match="not managed"):
        item.set("name", "after")

    assert item.get("name") == "before"
    assert len(item.history("name")) == 1


def test_cross_store_links_are_rejected_without_half_relation() -> None:
    left = Ontology()
    left.define_object_type("Source")
    left.define_object_type("Target")
    left.define_link_type("relates_to", "Source", "Target")
    source = left.create("Source")

    right = Ontology()
    right.define_object_type("Target")
    target = right.create("Target")

    with pytest.raises(ValueError, match="not managed"):
        source.link("relates_to", target)

    assert source.get_links("relates_to") == []
    assert target.get_incoming("relates_to") == []


def test_cardinality_failure_does_not_create_half_relation() -> None:
    ontology = Ontology()
    ontology.define_object_type("Source")
    ontology.define_object_type("Target")
    ontology.define_link_type(
        "relates_to",
        "Source",
        "Target",
        cardinality=Cardinality.ONE_TO_ONE,
    )
    source_1 = ontology.create("Source")
    source_2 = ontology.create("Source")
    target_1 = ontology.create("Target")
    target_2 = ontology.create("Target")
    source_1.link("relates_to", target_1)

    with pytest.raises(ValueError, match="cardinality"):
        source_1.link("relates_to", target_2)
    with pytest.raises(ValueError, match="cardinality"):
        source_2.link("relates_to", target_1)

    assert [link.target_id for link in source_1.get_links("relates_to")] == [
        target_1.id
    ]
    assert source_2.get_links("relates_to") == []
    assert target_2.get_incoming("relates_to") == []
    assert [link.target_id for link in target_1.get_incoming("relates_to")] == [
        source_1.id
    ]


def test_managed_object_unlink_routes_through_bidirectional_store_state() -> None:
    ontology = Ontology()
    ontology.define_object_type("Source")
    ontology.define_object_type("Target")
    ontology.define_link_type(
        "relates_to",
        "Source",
        "Target",
        cardinality=Cardinality.ONE_TO_ONE,
    )
    source = ontology.create("Source")
    old_target = ontology.create("Target")
    new_target = ontology.create("Target")
    source.link("relates_to", old_target, timestamp=10.0)

    source.unlink("relates_to", old_target, timestamp=20.0)
    source.link("relates_to", new_target, timestamp=30.0)

    assert source.get_links("relates_to", as_of=15.0)[0].target_id == old_target.id
    assert old_target.get_incoming("relates_to", as_of=15.0)[0].target_id == source.id
    assert old_target.get_incoming("relates_to") == []
    assert source.get_links("relates_to")[0].target_id == new_target.id


def test_fusion_updates_use_the_managed_index_boundary() -> None:
    ontology = Ontology()
    ontology.define_object_type(
        "Product",
        properties=[Property("name", str, indexed=True)],
    )
    fusion = DataFusion(ontology)
    fusion.register_mapping(
        SourceMapping(
            source_name="erp",
            object_type="Product",
            id_field="id",
            field_mappings=[FieldMapping("name", "name")],
        )
    )
    product = fusion.ingest("erp", [{"id": "P-1", "name": "old"}])[0]

    fusion.ingest("erp", [{"id": "P-1", "name": "new"}])

    assert ontology.find_by_property("name", "old", "Product") == []
    assert ontology.find_by_property("name", "new", "Product") == [product]
