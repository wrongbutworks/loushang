from __future__ import annotations

from pathlib import Path

from loushang.ontology import Ontology, Property
from loushang.ontology.query.contracts import (
    PropertyFilter,
    QueryRequest,
    StartFromType,
)
from loushang.ontology.storage import SQLiteObjectStore


def test_typed_query_reports_schema_and_projection_freshness() -> None:
    ontology = Ontology(package_id="test.query", schema_version="2.0.0")
    ontology.define_object_type(
        "Asset",
        properties=[Property("code", str, indexed=True), Property("score", int)],
    )
    selected = ontology.create("Asset", code="A-1", score=5)
    ontology.create("Asset", code="A-2", score=1)

    result = ontology.execute_query(
        QueryRequest(
            schema_version="2.0.0",
            steps=(
                StartFromType("Asset"),
                PropertyFilter("score", ">=", 5),
            ),
        )
    )

    assert result.object_ids == (selected.id,)
    assert result.schema_version == "2.0.0"
    assert result.projection.fresh is True
    assert result.diagnostics == ()


def test_query_schema_mismatch_is_visible_without_returning_objects() -> None:
    ontology = Ontology(package_id="test.query", schema_version="2.0.0")
    ontology.define_object_type("Asset")
    ontology.create("Asset")

    result = ontology.execute_query(
        QueryRequest(
            schema_version="1.0.0",
            steps=(StartFromType("Asset"),),
        )
    )

    assert result.object_ids == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "schema_version_mismatch"
    ]


def test_compatibility_query_builder_compiles_to_typed_request() -> None:
    ontology = Ontology()
    ontology.define_object_type("Asset", properties=[Property("score", int)])
    selected = ontology.create("Asset", score=5)
    ontology.create("Asset", score=1)

    result = (
        ontology.query()
        .start_from_type("Asset")
        .where("score", ">", 1)
        .execute_result()
    )

    assert result.object_ids == (selected.id,)
    assert result.projection.fresh is True


def test_facade_accepts_injected_sqlite_store_and_queries_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ontology.sqlite3"
    store = SQLiteObjectStore(database)
    ontology = Ontology(
        package_id="test.injected",
        schema_version="3.0.0",
        store=store,
    )
    ontology.define_object_type("Asset", properties=[Property("code", str, unique=True)])
    selected = ontology.create("Asset", code="A-1")
    store.close()

    reopened = SQLiteObjectStore(database)
    assert reopened.schema is not None
    restored = Ontology.from_schema(reopened.schema, store=reopened)
    result = restored.execute_query(
        QueryRequest(
            schema_version="3.0.0",
            steps=(StartFromType("Asset"),),
        )
    )

    assert result.object_ids == (selected.id,)
    assert result.projection.fresh is True
    reopened.close()
