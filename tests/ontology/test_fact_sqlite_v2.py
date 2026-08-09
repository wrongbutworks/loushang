from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

import pytest

from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactRecord,
    ObjectAssertion,
    PropertyAssertion,
    project_facts,
)
from loushang.ontology.schema import (
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
)
from loushang.ontology.storage import (
    SQLITE_STORAGE_FORMAT_VERSION,
    SQLiteFactStore,
    SQLiteStorageFormatError,
)

SUBJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
FACT_ID = UUID("10000000-0000-0000-0000-000000000001")
DERIVED_FACT_ID = UUID("10000000-0000-0000-0000-000000000002")
INFERRED_FACT_ID = UUID("10000000-0000-0000-0000-000000000003")


def _schema():
    return OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.sqlite-facts",
            namespace="urn:test:sqlite-facts",
            version="1.0.0",
            object_types=[ObjectTypeDefinition("Asset")],
        )
    )


def _batch() -> FactBatch:
    return FactBatch(
        "source.erp:batch-1",
        [
            FactRecord(
                fact_id=FACT_ID,
                subject_id=SUBJECT_ID,
                assertion=ObjectAssertion("Asset"),
                assertion_kind=AssertionKind.ASSERTED,
                source_ref="source.erp",
                source_record_ref="asset:A-1",
                evidence_refs=["evidence:row-1"],
                valid_from=0,
                recorded_at=10,
            )
        ],
    )


def _classification_batch() -> FactBatch:
    return FactBatch(
        "model:batch-1",
        [
            FactRecord(
                fact_id=DERIVED_FACT_ID,
                subject_id=SUBJECT_ID,
                assertion=PropertyAssertion("derived_signal", 0.8),
                assertion_kind=AssertionKind.DERIVED,
                source_ref="rule:1",
                source_record_ref="asset:A-1:derived",
                methodology_ref="method:derived",
                valid_from=0,
                recorded_at=30,
            ),
            FactRecord(
                fact_id=INFERRED_FACT_ID,
                subject_id=SUBJECT_ID,
                assertion=PropertyAssertion("inferred_signal", "likely"),
                assertion_kind=AssertionKind.INFERRED,
                source_ref="model:1",
                source_record_ref="asset:A-1:inferred",
                agent_ref="agent:1",
                confidence=0.7,
                valid_from=0,
                recorded_at=30,
            ),
        ],
    )


def test_sqlite_v2_records_fact_tables_and_watermark(tmp_path: Path) -> None:
    database = tmp_path / "facts.sqlite3"
    store = SQLiteFactStore(database)
    store.bind_schema(_schema())
    store.commit_fact_batch(_batch())
    store.close()

    with sqlite3.connect(database) as connection:
        tables = {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        metadata = dict(connection.execute("SELECT key, value FROM ontology_metadata"))

    assert SQLITE_STORAGE_FORMAT_VERSION == 2
    assert {"semantic_facts", "fact_batches"} <= tables
    assert metadata["fact_watermark"] == "1"


def test_sqlite_fact_commit_requires_a_bound_semantic_schema(tmp_path: Path) -> None:
    store = SQLiteFactStore(tmp_path / "unbound.sqlite3")

    assert not hasattr(store, "create")
    assert not hasattr(store, "set_property")
    assert not hasattr(store, "link_objects")

    with pytest.raises(RuntimeError, match="bound schema"):
        store.commit_fact_batch(_batch())

    assert store.fact_watermark == 0
    store.close()


def test_sqlite_v1_is_rejected_without_migration_or_mutation(tmp_path: Path) -> None:
    database = tmp_path / "v1.sqlite3"
    SQLiteFactStore(database).close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE ontology_metadata SET value = '1' "
            "WHERE key = 'storage_format_version'"
        )
    before = database.read_bytes()

    with pytest.raises(SQLiteStorageFormatError) as exc_info:
        SQLiteFactStore(database)

    assert exc_info.value.expected_version == 2
    assert exc_info.value.found_version == "1"
    assert database.read_bytes() == before


def test_sqlite_v2_rejects_an_incomplete_fact_layout(tmp_path: Path) -> None:
    database = tmp_path / "incomplete-v2.sqlite3"
    SQLiteFactStore(database).close()
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE semantic_facts")

    with pytest.raises(SQLiteStorageFormatError, match="incomplete"):
        SQLiteFactStore(database)


def test_sqlite_v2_restart_and_backup_restore_fact_authority_and_projection(
    tmp_path: Path,
) -> None:
    database = tmp_path / "facts.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    schema = _schema()
    store = SQLiteFactStore(database)
    store.bind_schema(schema)
    original = store.commit_fact_batch(_batch())
    store.commit_fact_batch(_classification_batch())
    store.backup_to(backup)
    store.close()

    restored = SQLiteFactStore(backup, expected_schema=schema)
    assert restored.fact_watermark == 3
    assert restored.get_fact(FACT_ID).fact.evidence_refs == ("evidence:row-1",)
    assert (
        restored.get_fact(DERIVED_FACT_ID).fact.assertion_kind
        is AssertionKind.DERIVED
    )
    assert (
        restored.get_fact(INFERRED_FACT_ID).fact.assertion_kind
        is AssertionKind.INFERRED
    )
    replay = restored.commit_fact_batch(FactBatch.from_json(_batch().to_json()))
    assert replay.first_sequence == original.first_sequence
    assert replay.last_sequence == original.last_sequence
    assert replay.replayed is True
    projection = project_facts(restored, schema, valid_at=20, recorded_at=20)
    assert projection.view.get(SUBJECT_ID) is not None
    restored.close()


def test_failed_sqlite_fact_transaction_leaves_memory_and_watermark_unchanged(
    tmp_path: Path,
) -> None:
    database = tmp_path / "facts.sqlite3"
    store = SQLiteFactStore(database)
    store.bind_schema(_schema())
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TRIGGER reject_fact
            BEFORE INSERT ON fact_batches
            BEGIN
                SELECT RAISE(ABORT, 'fact rejected');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="fact rejected"):
        store.commit_fact_batch(_batch())

    assert store.fact_watermark == 0
    assert store.read_facts() == ()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM semantic_facts").fetchone() == (
            0,
        )
        assert connection.execute("SELECT COUNT(*) FROM fact_batches").fetchone() == (0,)
        connection.execute("DROP TRIGGER reject_fact")
    assert store.commit_fact_batch(_batch()).last_sequence == 1
    store.close()


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        (
            "UPDATE semantic_facts SET payload = '{not-json' WHERE sequence = 1",
            "runtime data",
        ),
        (
            "UPDATE ontology_metadata SET value = '2' WHERE key = 'fact_watermark'",
            "fact watermark",
        ),
        (
            "UPDATE semantic_facts SET fact_id = "
            "'10000000-0000-0000-0000-000000000099' WHERE sequence = 1",
            "identity",
        ),
        (
            "UPDATE fact_batches SET digest = "
            "'0000000000000000000000000000000000000000000000000000000000000000'",
            "digest",
        ),
    ],
)
def test_sqlite_v2_rejects_corrupt_fact_state(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    database = tmp_path / "facts.sqlite3"
    store = SQLiteFactStore(database)
    store.bind_schema(_schema())
    store.commit_fact_batch(_batch())
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute(corruption)

    with pytest.raises(SQLiteStorageFormatError, match=message):
        SQLiteFactStore(database)
