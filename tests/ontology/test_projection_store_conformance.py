from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactRecord,
    FactStore,
    LinkAssertion,
    ObjectAssertion,
    PropertyAssertion,
)
from loushang.ontology.projection import (
    ProjectionReadStore,
    ProjectionStore,
    ProjectionUnavailableError,
    materialize_projection,
)
from loushang.ontology.query import QueryBuilder
from loushang.ontology.schema import (
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    ValueType,
)
from loushang.ontology.storage import (
    MemoryFactStore,
    MemoryProjectionStore,
    SQLiteFactStore,
    SQLiteProjectionStore,
    SQLiteStorageFormatError,
)

ASSET_ID = UUID("00000000-0000-0000-0000-000000000001")
OWNER_ID = UUID("00000000-0000-0000-0000-000000000002")
SCORE_ID = UUID("10000000-0000-0000-0000-000000000003")


def _schema():
    return OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.projection-store",
            namespace="urn:test:projection-store",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    "Asset",
                    properties=[
                        PropertyDefinition("code", ValueType.STRING, required=True),
                        PropertyDefinition("score", ValueType.INTEGER),
                    ],
                ),
                ObjectTypeDefinition("Owner"),
            ],
            link_types=[LinkTypeDefinition("owned_by", "Asset", "Owner")],
        )
    )


def _fact(
    suffix: int,
    subject_id: UUID,
    assertion: object,
    *,
    source_record_ref: str | None = None,
    recorded_at: float = 1,
    supersedes: UUID | None = None,
) -> FactRecord:
    return FactRecord(
        fact_id=UUID(f"10000000-0000-0000-0000-{suffix:012d}"),
        subject_id=subject_id,
        assertion=assertion,  # type: ignore[arg-type]
        assertion_kind=AssertionKind.ASSERTED,
        source_ref="source.erp",
        source_record_ref=source_record_ref or f"record:{suffix}",
        valid_from=0,
        recorded_at=recorded_at,
        supersedes=supersedes,
    )


def _initial_batch() -> FactBatch:
    return FactBatch(
        "initial",
        [
            _fact(1, ASSET_ID, ObjectAssertion("Asset")),
            _fact(2, ASSET_ID, PropertyAssertion("code", "A-1")),
            _fact(
                3,
                ASSET_ID,
                PropertyAssertion("score", 1),
                source_record_ref="asset:A-1:score",
            ),
            _fact(4, OWNER_ID, ObjectAssertion("Owner")),
            _fact(5, ASSET_ID, LinkAssertion("owned_by", OWNER_ID)),
        ],
    )


def _score_update() -> FactBatch:
    return FactBatch(
        "score-update",
        [
            _fact(
                6,
                ASSET_ID,
                PropertyAssertion("score", 2),
                source_record_ref="asset:A-1:score",
                recorded_at=20,
                supersedes=SCORE_ID,
            )
        ],
    )


@pytest.fixture(params=("memory", "sqlite"))
def stores(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[tuple[FactStore, ProjectionStore]]:
    if request.param == "memory":
        yield MemoryFactStore(), MemoryProjectionStore()
        return
    database = tmp_path / "ontology.sqlite3"
    facts = SQLiteFactStore(database)
    projections = SQLiteProjectionStore(database)
    try:
        yield facts, projections
    finally:
        projections.close()
        facts.close()


def test_projection_adapters_share_the_atomic_replacement_read_contract(
    stores: tuple[FactStore, ProjectionStore],
) -> None:
    facts, projections = stores
    schema = _schema()
    if isinstance(facts, SQLiteFactStore):
        facts.bind_schema(schema)
    facts.commit_fact_batch(_initial_batch())
    snapshot = materialize_projection(facts, schema, valid_at=10, recorded_at=10)

    with pytest.raises(ProjectionUnavailableError):
        projections.all_objects()
    state = projections.replace(snapshot)

    assert isinstance(projections, ProjectionReadStore)
    assert isinstance(projections, ProjectionStore)
    assert state.fresh is True
    assert projections.read_snapshot().projection_state == state
    assert projections.get(ASSET_ID).get("score") == 1  # type: ignore[union-attr]
    assert projections.find_neighbors(ASSET_ID, "owned_by") == (
        projections.get(OWNER_ID),
    )
    assert QueryBuilder(projections).start_from_type("Asset").execute_ids() == [
        ASSET_ID
    ]
    assert not hasattr(projections, "create")
    assert not hasattr(projections, "set_property")
    assert not hasattr(projections, "link_objects")


def test_projection_rebuild_replaces_the_whole_snapshot_monotonically(
    stores: tuple[FactStore, ProjectionStore],
) -> None:
    facts, projections = stores
    schema = _schema()
    if isinstance(facts, SQLiteFactStore):
        facts.bind_schema(schema)
    facts.commit_fact_batch(_initial_batch())
    first = materialize_projection(facts, schema, valid_at=10, recorded_at=10)
    projections.replace(first)

    rebuilt = materialize_projection(
        facts,
        schema,
        valid_at=10,
        recorded_at=10,
        projection_version=2,
    )
    projections.replace(rebuilt)

    assert projections.projection_state.projection_version == 2
    assert projections.all_objects() == rebuilt.objects
    with pytest.raises(ValueError, match="projection_version must be 3"):
        projections.replace(rebuilt)


def test_sqlite_projection_restart_and_fact_commit_expose_staleness(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ontology.sqlite3"
    schema = _schema()
    facts = SQLiteFactStore(database)
    facts.bind_schema(schema)
    facts.commit_fact_batch(_initial_batch())
    projection = SQLiteProjectionStore(database)
    projection.replace(
        materialize_projection(facts, schema, valid_at=10, recorded_at=10)
    )
    projection.close()

    reopened = SQLiteProjectionStore(database, expected_schema=schema)
    assert reopened.get(ASSET_ID).get("score") == 1  # type: ignore[union-attr]
    assert reopened.projection_state.fresh is True

    facts.commit_fact_batch(_score_update())
    assert reopened.projection_state.fresh is False
    assert reopened.projection_state.source_fact_watermark == 6
    assert reopened.projection_state.projected_fact_watermark == 5
    assert reopened.get(ASSET_ID).get("score") == 1  # type: ignore[union-attr]
    reopened.close()
    facts.close()


def test_fact_commit_survives_projection_replacement_failure(tmp_path: Path) -> None:
    database = tmp_path / "ontology.sqlite3"
    schema = _schema()
    facts = SQLiteFactStore(database)
    facts.bind_schema(schema)
    facts.commit_fact_batch(_initial_batch())
    projection = SQLiteProjectionStore(database)
    projection.replace(
        materialize_projection(facts, schema, valid_at=10, recorded_at=10)
    )

    facts.commit_fact_batch(_score_update())
    replacement = materialize_projection(
        facts,
        schema,
        valid_at=30,
        recorded_at=30,
        projection_version=2,
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TRIGGER reject_projection
            BEFORE UPDATE ON projection_metadata
            BEGIN
                SELECT RAISE(ABORT, 'projection rejected');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="projection rejected"):
        projection.replace(replacement)

    assert facts.fact_watermark == 6
    assert facts.get_fact(UUID("10000000-0000-0000-0000-000000000006"))
    assert projection.get(ASSET_ID).get("score") == 1  # type: ignore[union-attr]
    assert projection.projection_state.projection_version == 1
    assert projection.projection_state.fresh is False

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER reject_projection")
    projection.replace(replacement)
    assert projection.get(ASSET_ID).get("score") == 2  # type: ignore[union-attr]
    projection.close()
    facts.close()


def test_sqlite_rejects_corrupt_projection_rows_on_reopen(tmp_path: Path) -> None:
    database = tmp_path / "ontology.sqlite3"
    schema = _schema()
    facts = SQLiteFactStore(database)
    facts.bind_schema(schema)
    facts.commit_fact_batch(_initial_batch())
    projection = SQLiteProjectionStore(database)
    projection.replace(
        materialize_projection(facts, schema, valid_at=10, recorded_at=10)
    )
    projection.close()
    facts.close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE projection_properties SET value_json = '{not-json' "
            "WHERE property_name = 'score'"
        )

    with pytest.raises(SQLiteStorageFormatError, match="runtime data"):
        SQLiteProjectionStore(database)
