"""本体核心模块测试."""

import pytest

from loushang.ontology import (
    Cardinality,
    LinkType,
    ObjectType,
    Ontology,
    Property,
)


class TestProperty:
    def test_property_creation(self) -> None:
        prop = Property("name", str, required=True, indexed=True)
        assert prop.name == "name"
        assert prop.data_type is str
        assert prop.required is True
        assert prop.indexed is True

    def test_property_validation_required(self) -> None:
        prop = Property("name", str, required=True)
        with pytest.raises(ValueError, match="required"):
            prop.validate(None)

    def test_property_validation_optional(self) -> None:
        prop = Property("age", int, required=False)
        prop.validate(None)  # should not raise

    def test_property_validation_custom(self) -> None:
        prop = Property("score", int, validator=lambda x: 0 <= x <= 100)
        prop.validate(50)
        with pytest.raises(ValueError):
            prop.validate(150)


class TestLinkType:
    def test_cardinality(self) -> None:
        lt = LinkType("owns", "Person", "Company", cardinality=Cardinality.ONE_TO_MANY)
        assert lt.allows_multiple_targets() is True
        assert lt.allows_multiple_sources() is False


class TestObjectType:
    def test_get_property(self) -> None:
        ot = ObjectType(
            "Person",
            properties=[Property("name", str), Property("age", int)],
        )
        assert ot.get_property("name") is not None
        assert ot.get_property("missing") is None

    def test_validate_properties(self) -> None:
        ot = ObjectType(
            "Person",
            properties=[Property("name", str, required=True)],
        )
        with pytest.raises(ValueError, match="Required"):
            ot.validate_properties({})

        result = ot.validate_properties({"name": "Alice"})
        assert result["name"] == "Alice"

    def test_validate_with_default(self) -> None:
        ot = ObjectType(
            "Person",
            properties=[Property("status", str, required=True, default="active")],
        )
        result = ot.validate_properties({})
        assert result["status"] == "active"


class TestOntology:
    def test_define_and_create(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Person",
            properties=[
                Property("name", str, required=True),
                Property("age", int),
            ],
        )

        person = onto.create("Person", name="Alice", age=30)
        assert person.object_type == "Person"
        assert person.get("name") == "Alice"
        assert person.get("age") == 30

    def test_unregistered_type(self) -> None:
        onto = Ontology()
        with pytest.raises(ValueError, match="not registered"):
            onto.create("Unknown", name="test")

    def test_link_objects(self) -> None:
        onto = Ontology()
        onto.define_object_type("Person", properties=[Property("name", str)])
        onto.define_object_type("Company", properties=[Property("name", str)])
        onto.define_link_type("works_for", "Person", "Company")

        alice = onto.create("Person", name="Alice")
        acme = onto.create("Company", name="ACME")

        onto.link(alice, "works_for", acme)

        neighbors = onto._store.find_neighbors(alice.id, "works_for")
        assert len(neighbors) == 1
        assert neighbors[0].id == acme.id

    def test_link_type_mismatch(self) -> None:
        onto = Ontology()
        onto.define_object_type("Person", properties=[Property("name", str)])
        onto.define_object_type("Company", properties=[Property("name", str)])
        onto.define_link_type("works_for", "Person", "Company")

        acme = onto.create("Company", name="ACME")
        other = onto.create("Company", name="Other")

        with pytest.raises(TypeError):
            onto.link(acme, "works_for", other)

    def test_find_by_property(self) -> None:
        onto = Ontology()
        onto.define_object_type(
            "Person",
            properties=[Property("name", str, indexed=True), Property("age", int)],
        )

        onto.create("Person", name="Alice", age=30)
        onto.create("Person", name="Bob", age=25)
        onto.create("Person", name="Alice", age=35)

        results = onto.find_by_property("name", "Alice")
        assert len(results) == 2

    def test_query_chain(self) -> None:
        onto = Ontology()
        onto.define_object_type("Person", properties=[Property("name", str)])
        onto.define_object_type("Company", properties=[Property("name", str), Property("industry", str)])
        onto.define_link_type("works_for", "Person", "Company")

        alice = onto.create("Person", name="Alice")
        acme = onto.create("Company", name="ACME", industry="tech")
        oldcorp = onto.create("Company", name="OldCorp", industry="finance")

        onto.link(alice, "works_for", acme)
        onto.link(alice, "works_for", oldcorp)

        results = (
            onto.query()
            .start_from(alice)
            .follow("works_for")
            .where("industry", "==", "tech")
            .execute()
        )
        assert len(results) == 1
        assert results[0].get("name") == "ACME"

    def test_query_limit_offset(self) -> None:
        onto = Ontology()
        onto.define_object_type("Item", properties=[Property("value", int)])

        for i in range(10):
            onto.create("Item", value=i)

        all_items = onto.find_by_type("Item")
        assert len(all_items) == 10

    def test_temporal_properties(self) -> None:
        import time

        onto = Ontology()
        onto.define_object_type("Sensor", properties=[Property("reading", float)])

        base = time.time()
        sensor = onto.create("Sensor", reading=10.0)
        sensor.set("reading", 20.0, timestamp=base + 1000.0)
        sensor.set("reading", 30.0, timestamp=base + 2000.0)

        assert sensor.get("reading") == 30.0
        assert sensor.get("reading", as_of=base + 1500.0) == 20.0
        assert sensor.get("reading", as_of=base + 500.0) == 10.0

        history = sensor.history("reading")
        assert len(history) == 3

    def test_temporal_links(self) -> None:
        import time

        onto = Ontology()
        onto.define_object_type("Person", properties=[Property("name", str)])
        onto.define_object_type("Company", properties=[Property("name", str)])
        onto.define_link_type("works_for", "Person", "Company")

        base = time.time()
        alice = onto.create("Person", name="Alice")
        acme = onto.create("Company", name="ACME")
        oldcorp = onto.create("Company", name="OldCorp")

        onto.link(alice, "works_for", oldcorp, timestamp=base + 1000.0)
        onto.unlink(alice, "works_for", oldcorp, timestamp=base + 2000.0)
        onto.link(alice, "works_for", acme, timestamp=base + 2000.0)

        # 当前状态
        current = onto._store.find_neighbors(alice.id, "works_for", as_of=None)
        assert len(current) == 1
        assert current[0].get("name") == "ACME"

        # 历史状态
        past = onto._store.find_neighbors(alice.id, "works_for", as_of=base + 1500.0)
        assert len(past) == 1
        assert past[0].get("name") == "OldCorp"

    def test_delete_object(self) -> None:
        onto = Ontology()
        onto.define_object_type("Item", properties=[Property("name", str, indexed=True)])

        item = onto.create("Item", name="to_delete")
        item_id = item.id

        assert onto.get(item_id) is not None
        assert onto.delete(item_id) is True
        assert onto.get(item_id) is None
        assert onto.delete(item_id) is False

    def test_query_as_of(self) -> None:
        import time

        onto = Ontology()
        onto.define_object_type("Person", properties=[Property("name", str)])
        onto.define_object_type("Company", properties=[Property("name", str)])
        onto.define_link_type("works_for", "Person", "Company")

        base = time.time()
        alice = onto.create("Person", name="Alice")
        acme = onto.create("Company", name="ACME")
        oldcorp = onto.create("Company", name="OldCorp")

        onto.link(alice, "works_for", oldcorp, timestamp=base + 1000.0)
        onto.link(alice, "works_for", acme, timestamp=base + 2000.0)

        # 查询历史快照
        results = (
            onto.query()
            .start_from(alice)
            .as_of(base + 1500.0)
            .follow("works_for")
            .execute()
        )
        assert len(results) == 1
        assert results[0].get("name") == "OldCorp"

    def test_incoming_links(self) -> None:
        onto = Ontology()
        onto.define_object_type("Person", properties=[Property("name", str)])
        onto.define_object_type("Company", properties=[Property("name", str)])
        onto.define_link_type(
            "works_for",
            "Person",
            "Company",
            cardinality=Cardinality.MANY_TO_ONE,
        )

        alice = onto.create("Person", name="Alice")
        bob = onto.create("Person", name="Bob")
        acme = onto.create("Company", name="ACME")

        onto.link(alice, "works_for", acme)
        onto.link(bob, "works_for", acme)

        # 从 Company 查 incoming
        incoming = acme.get_incoming("works_for")
        assert len(incoming) == 2
        source_ids = {link.target_id for link in incoming}
        assert alice.id in source_ids
        assert bob.id in source_ids
