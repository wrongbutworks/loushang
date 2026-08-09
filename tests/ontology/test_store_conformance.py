from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

from loushang.ontology.core.store import ObjectStore
from loushang.ontology.schema import (
    LinkCardinality,
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    ValueType,
)
from loushang.ontology.storage.sqlite import (
    _SQLiteObjectStore as SQLiteProjectionBackend,
)

StoreFactory = Callable[[], ObjectStore]


def _compiled_schema():
    return OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.store",
            namespace="urn:test:store",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    name="Asset",
                    properties=[
                        PropertyDefinition(
                            "code",
                            ValueType.STRING,
                            required=True,
                            unique=True,
                            indexed=True,
                        ),
                        PropertyDefinition("score", ValueType.INTEGER),
                    ],
                ),
                ObjectTypeDefinition(name="Owner"),
            ],
            link_types=[
                LinkTypeDefinition(
                    name="owned_by",
                    source_type="Asset",
                    target_type="Owner",
                    cardinality=LinkCardinality.MANY_TO_ONE,
                )
            ],
        )
    )


@pytest.fixture(params=("memory", "sqlite"))
def store_factory(request: pytest.FixtureRequest, tmp_path: Path) -> StoreFactory:
    if request.param == "memory":
        return ObjectStore
    database = tmp_path / "ontology.sqlite3"
    return lambda: SQLiteProjectionBackend(database)


def test_memory_and_sqlite_share_mutation_projection_contract(
    store_factory: StoreFactory,
) -> None:
    store = store_factory()
    store.bind_schema(_compiled_schema())
    asset = store.create(
        "Asset",
        {"code": "A-1", "score": 1},
        obj_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    owner = store.create(
        "Owner",
        obj_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    store.set_property(asset, "score", 2, timestamp=20.0, author="actor")
    store.link_objects(asset, "owned_by", owner, timestamp=30.0, properties={"source": "test"})

    assert store.current_watermark == 4
    assert [record.sequence for record in store.read_mutations()] == [1, 2, 3, 4]
    exposed_payload = store.read_mutations()[0].payload
    exposed_payload["object_type"] = "changed"
    assert store.read_mutations()[0].payload["object_type"] == "Asset"
    assert store.projection_state.fresh is True
    assert store.projection_state.projected_watermark == 4
    assert store.find_by_property("code", "A-1", "Asset") == [asset]
    assert store.find_neighbors(asset.id, "owned_by") == [owner]

    rebuilt = store.rebuild_projections()
    assert rebuilt.fresh is True
    assert rebuilt.projected_watermark == 4
    assert rebuilt.projection_version == 2
    assert store.find_by_property("code", "A-1", "Asset") == [asset]
    assert store.find_neighbors(asset.id, "owned_by") == [owner]


def test_rejected_mutations_do_not_advance_store_watermarks(
    store_factory: StoreFactory,
) -> None:
    store = store_factory()
    store.bind_schema(_compiled_schema())
    first = store.create("Asset", {"code": "A-1"})
    owner = store.create("Owner")
    store.link_objects(first, "owned_by", owner)
    watermark = store.current_watermark

    with pytest.raises(ValueError, match="unique"):
        store.create("Asset", {"code": "A-1"})
    with pytest.raises(ValueError, match="active link"):
        store.delete(owner.id)

    assert store.current_watermark == watermark
    assert store.projection_state.projected_watermark == watermark
    assert store.count() == 2


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"timestamp": float("nan")}, "finite number"),
        ({"author": 7}, "author must be a string"),
    ],
)
def test_invalid_mutation_metadata_is_rejected_before_commit(
    store_factory: StoreFactory,
    kwargs: dict[str, object],
    error: str,
) -> None:
    store = store_factory()
    store.bind_schema(_compiled_schema())
    asset = store.create("Asset", {"code": "A-1", "score": 1})
    watermark = store.current_watermark

    with pytest.raises((TypeError, ValueError), match=error):
        store.set_property(asset, "score", 2, **kwargs)  # type: ignore[arg-type]

    assert asset.get("score") == 1
    assert store.current_watermark == watermark
    assert store.projection_state.projected_watermark == watermark
    assert store.count() == 1


def test_sqlite_restart_restores_authority_history_and_projection(tmp_path: Path) -> None:
    database = tmp_path / "ontology.sqlite3"
    store = SQLiteProjectionBackend(database)
    schema = _compiled_schema()
    store.bind_schema(schema)
    asset = store.create("Asset", {"code": "A-1", "score": 1})
    owner = store.create("Owner")
    store.set_property(asset, "score", 2, timestamp=20.0, source="import")
    store.link_objects(asset, "owned_by", owner, timestamp=30.0)
    asset_id = asset.id
    owner_id = owner.id
    store.close()

    reopened = SQLiteProjectionBackend(database)
    restored = reopened.get(asset_id)
    assert reopened.schema == schema
    assert restored is not None
    assert restored.get("score") == 2
    history = restored.history("score")
    assert len(history) == 2
    assert history[1].timestamp == 20.0
    assert [item.id for item in reopened.find_neighbors(asset_id, "owned_by")] == [
        owner_id
    ]
    assert reopened.find_by_property("code", "A-1", "Asset") == [restored]
    assert reopened.current_watermark == 4
    assert reopened.projection_state.fresh is True
    reopened.close()


def test_required_links_are_checked_explicitly_without_blocking_object_creation(
    store_factory: StoreFactory,
) -> None:
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.required-link",
            namespace="urn:test:required-link",
            version="1.0.0",
            object_types=[ObjectTypeDefinition("Source"), ObjectTypeDefinition("Target")],
            link_types=[
                LinkTypeDefinition("target", "Source", "Target", required=True)
            ],
        )
    )
    store = store_factory()
    store.bind_schema(schema)
    source = store.create("Source")
    target = store.create("Target")

    assert [item.code for item in store.validate_integrity()] == [
        "required_link_missing"
    ]

    store.link_objects(source, "target", target)
    assert store.validate_integrity() == ()


def test_link_properties_use_the_strict_foundation_json_contract(
    store_factory: StoreFactory,
) -> None:
    store = store_factory()
    store.bind_schema(_compiled_schema())
    asset = store.create("Asset", {"code": "A-1"})
    owner = store.create("Owner")
    watermark = store.current_watermark

    with pytest.raises(TypeError, match="JSON-safe"):
        store.link_objects(asset, "owned_by", owner, properties={"bad": (1, 2)})

    assert store.current_watermark == watermark


def test_inherited_unique_property_keeps_its_declaring_identity(
    store_factory: StoreFactory,
) -> None:
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.unique-inheritance",
            namespace="urn:test:unique-inheritance",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    "Base",
                    properties=[
                        PropertyDefinition("code", ValueType.STRING, unique=True)
                    ],
                ),
                ObjectTypeDefinition("Child", parent_types=["Base"]),
                ObjectTypeDefinition(
                    "Override",
                    parent_types=["Base"],
                    properties=[
                        PropertyDefinition("code", ValueType.STRING, unique=True)
                    ],
                ),
            ],
        )
    )
    store = store_factory()
    store.bind_schema(schema)
    store.create("Base", {"code": "same"})

    with pytest.raises(ValueError, match="unique"):
        store.create("Child", {"code": "same"})

    store.create("Override", {"code": "same"})


def test_property_index_does_not_hide_an_unindexed_same_named_property(
    store_factory: StoreFactory,
) -> None:
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.index-scope",
            namespace="urn:test:index-scope",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    "Indexed",
                    properties=[
                        PropertyDefinition("code", ValueType.STRING, indexed=True)
                    ],
                ),
                ObjectTypeDefinition(
                    "Unindexed",
                    properties=[PropertyDefinition("code", ValueType.STRING)],
                ),
            ],
        )
    )
    store = store_factory()
    store.bind_schema(schema)
    indexed = store.create("Indexed", {"code": "same"})
    unindexed = store.create("Unindexed", {"code": "same"})

    assert store.find_by_property("code", "same", "Indexed") == [indexed]
    assert store.find_by_property("code", "same", "Unindexed") == [unindexed]
    assert set(store.find_by_property("code", "same")) == {indexed, unindexed}


def test_sqlite_transaction_failure_restores_last_committed_state(tmp_path: Path) -> None:
    database = tmp_path / "ontology.sqlite3"
    store = SQLiteProjectionBackend(database)
    store.bind_schema(_compiled_schema())
    asset = store.create("Asset", {"code": "A-1", "score": 1})
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TRIGGER reject_test_mutation
            BEFORE INSERT ON mutation_journal
            BEGIN
                SELECT RAISE(ABORT, 'test rejection');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="test rejection"):
        store.set_property(asset, "score", 2)

    assert store.get(asset.id) is asset
    assert asset.get("score") == 1
    assert store.count() == 1
    assert store.current_watermark == 1
    assert store.projection_state.projected_watermark == 1

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER reject_test_mutation")
    asset.set("score", 3)
    assert asset.get("score") == 3
    assert store.current_watermark == 2
    store.close()
