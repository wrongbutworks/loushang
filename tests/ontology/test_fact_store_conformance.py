from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactBatchConflictError,
    FactReadStore,
    FactRecord,
    FactStore,
    FactValidationError,
    ObjectAssertion,
    PropertyAssertion,
)
from loushang.ontology.schema import (
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
)
from loushang.ontology.storage import MemoryFactStore, SQLiteFactStore

SUBJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
FACT_1 = UUID("10000000-0000-0000-0000-000000000001")
FACT_2 = UUID("10000000-0000-0000-0000-000000000002")
FACT_3 = UUID("10000000-0000-0000-0000-000000000003")


def _schema():
    return OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.facts",
            namespace="urn:test:facts",
            version="1.0.0",
            object_types=[ObjectTypeDefinition("Asset", semantic_id="asset")],
        )
    )


def _fact(
    fact_id: UUID,
    value: object,
    *,
    recorded_at: float,
    valid_from: float = 0.0,
    valid_to: float | None = None,
    supersedes: UUID | None = None,
    corrects: UUID | None = None,
    assertion_kind: AssertionKind = AssertionKind.ASSERTED,
) -> FactRecord:
    return FactRecord(
        fact_id=fact_id,
        subject_id=SUBJECT_ID,
        assertion=PropertyAssertion("status", value),
        assertion_kind=assertion_kind,
        source_ref="source.erp",
        source_record_ref="asset:A-1:status",
        valid_from=valid_from,
        valid_to=valid_to,
        recorded_at=recorded_at,
        supersedes=supersedes,
        corrects=corrects,
    )


@pytest.fixture(params=("memory", "sqlite"))
def fact_store(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[FactStore]:
    if request.param == "memory":
        yield MemoryFactStore()
        return
    store = SQLiteFactStore(tmp_path / "facts.sqlite3")
    store.bind_schema(_schema())
    try:
        yield store
    finally:
        store.close()


def test_fact_store_appends_contiguous_records_and_replays_batch_idempotently(
    fact_store: FactStore,
) -> None:
    first = _fact(FACT_1, "planned", recorded_at=10.0)
    second = _fact(
        FACT_2,
        "active",
        recorded_at=20.0,
        assertion_kind=AssertionKind.DERIVED,
    )
    batch = FactBatch("batch-1", [first, second])

    committed = fact_store.commit_fact_batch(batch)
    replayed = fact_store.commit_fact_batch(FactBatch.from_json(batch.to_json()))

    assert (committed.first_sequence, committed.last_sequence) == (1, 2)
    assert committed.fact_count == 2
    assert committed.replayed is False
    assert replayed.first_sequence == 1
    assert replayed.last_sequence == 2
    assert replayed.replayed is True
    assert fact_store.fact_watermark == 2
    assert [item.sequence for item in fact_store.read_facts()] == [1, 2]
    assert fact_store.get_fact(FACT_2).fact.assertion_kind is AssertionKind.DERIVED


def test_reusing_batch_id_with_other_content_is_rejected_atomically(
    fact_store: FactStore,
) -> None:
    fact_store.commit_fact_batch(FactBatch("batch-1", [_fact(FACT_1, "old", recorded_at=1)]))

    with pytest.raises(FactBatchConflictError, match="batch-1"):
        fact_store.commit_fact_batch(
            FactBatch("batch-1", [_fact(FACT_2, "different", recorded_at=2)])
        )

    assert fact_store.fact_watermark == 1
    assert len(fact_store.read_facts()) == 1


def test_bitemporal_selection_preserves_history_across_correction(
    fact_store: FactStore,
) -> None:
    original = _fact(FACT_1, "draft", recorded_at=10.0, valid_from=0.0)
    correction = _fact(
        FACT_2,
        "approved",
        recorded_at=30.0,
        valid_from=0.0,
        corrects=FACT_1,
    )
    future = _fact(
        FACT_3,
        "closed",
        recorded_at=40.0,
        valid_from=50.0,
        supersedes=FACT_2,
    )
    fact_store.commit_fact_batch(FactBatch("history", [original, correction, future]))

    known_at_20 = fact_store.select_facts(valid_at=25.0, recorded_at=20.0)
    known_at_35 = fact_store.select_facts(valid_at=25.0, recorded_at=35.0)
    valid_at_50 = fact_store.select_facts(valid_at=50.0, recorded_at=50.0)

    assert [item.fact.fact_id for item in known_at_20.facts] == [FACT_1]
    assert [item.fact.fact_id for item in known_at_35.facts] == [FACT_2]
    assert [item.fact.fact_id for item in valid_at_50.facts] == [FACT_3]
    assert known_at_20.fact_watermark == 3
    assert known_at_20.valid_at == 25
    assert known_at_20.recorded_at == 20
    assert fact_store.select_facts(valid_at=49.999, recorded_at=50.0).facts == ()


def test_retraction_is_an_append_only_validity_correction(
    fact_store: FactStore,
) -> None:
    original = _fact(FACT_1, "active", recorded_at=10.0, valid_from=0.0)
    retraction = _fact(
        FACT_2,
        "active",
        recorded_at=50.0,
        valid_from=0.0,
        valid_to=50.0,
        corrects=FACT_1,
    )
    fact_store.commit_fact_batch(FactBatch("retraction", [original, retraction]))

    assert [
        item.fact.fact_id
        for item in fact_store.select_facts(
            valid_at=49.999,
            recorded_at=60.0,
        ).facts
    ] == [FACT_2]
    assert fact_store.select_facts(valid_at=50.0, recorded_at=60.0).facts == ()
    assert [
        item.fact.fact_id
        for item in fact_store.select_facts(
            valid_at=50.0,
            recorded_at=20.0,
        ).facts
    ] == [FACT_1]


@pytest.mark.parametrize(
    ("replacement", "error"),
    [
        (
            FactRecord(
                fact_id=FACT_2,
                subject_id=SUBJECT_ID,
                assertion=PropertyAssertion("status", "new"),
                assertion_kind=AssertionKind.ASSERTED,
                source_ref="source.erp",
                source_record_ref="asset:A-1:status",
                valid_from=0,
                recorded_at=2,
                supersedes=FACT_3,
            ),
            "unknown",
        ),
        (
            FactRecord(
                fact_id=FACT_2,
                subject_id=SUBJECT_ID,
                assertion=PropertyAssertion("other", "new"),
                assertion_kind=AssertionKind.ASSERTED,
                source_ref="source.erp",
                source_record_ref="asset:A-1:status",
                valid_from=0,
                recorded_at=2,
                supersedes=FACT_1,
            ),
            "coordinate",
        ),
        (
            FactRecord(
                fact_id=FACT_2,
                subject_id=SUBJECT_ID,
                assertion=PropertyAssertion("status", "new"),
                assertion_kind=AssertionKind.ASSERTED,
                source_ref="source.other",
                source_record_ref="asset:A-1:status",
                valid_from=0,
                recorded_at=2,
                supersedes=FACT_1,
            ),
            "source lineage",
        ),
        (
            FactRecord(
                fact_id=FACT_2,
                subject_id=SUBJECT_ID,
                assertion=PropertyAssertion("status", "new"),
                assertion_kind=AssertionKind.DERIVED,
                source_ref="source.erp",
                source_record_ref="asset:A-1:status",
                valid_from=0,
                recorded_at=2,
                supersedes=FACT_1,
            ),
            "coordinate",
        ),
    ],
)
def test_invalid_lineage_rejects_the_whole_batch(
    fact_store: FactStore,
    replacement: FactRecord,
    error: str,
) -> None:
    original = _fact(FACT_1, "old", recorded_at=1)

    with pytest.raises(FactValidationError, match=error):
        fact_store.commit_fact_batch(FactBatch("invalid", [original, replacement]))

    assert fact_store.fact_watermark == 0
    assert fact_store.read_facts() == ()


def test_read_port_is_runtime_checkable(fact_store: FactStore) -> None:
    fact_store.commit_fact_batch(
        FactBatch(
            "objects",
            [
                FactRecord(
                    fact_id=FACT_1,
                    subject_id=SUBJECT_ID,
                    assertion=ObjectAssertion("Asset"),
                    assertion_kind=AssertionKind.INFERRED,
                    source_ref="model:1",
                    source_record_ref="asset:A-1",
                    valid_from=0,
                    recorded_at=1,
                )
            ],
        )
    )

    assert isinstance(fact_store, FactReadStore)
    assert fact_store.read_facts(after_sequence=1) == ()


def test_fact_store_rejects_duplicate_identity_and_invalid_read_coordinates(
    fact_store: FactStore,
) -> None:
    fact_store.commit_fact_batch(FactBatch("first", [_fact(FACT_1, "old", recorded_at=1)]))

    with pytest.raises(FactValidationError, match="already committed"):
        fact_store.commit_fact_batch(
            FactBatch("duplicate", [_fact(FACT_1, "again", recorded_at=2)])
        )
    with pytest.raises(KeyError, match="Unknown ontology fact"):
        fact_store.get_fact(FACT_3)
    with pytest.raises(ValueError, match="after_sequence"):
        fact_store.read_facts(after_sequence=-1)
    with pytest.raises(ValueError, match="recorded_at"):
        fact_store.select_facts(valid_at=1, recorded_at=float("nan"))

    assert fact_store.fact_watermark == 1


def test_fact_lineage_rejects_earlier_recording_and_multiple_successors(
    fact_store: FactStore,
) -> None:
    original = _fact(FACT_1, "old", recorded_at=10)
    fact_store.commit_fact_batch(FactBatch("original", [original]))

    with pytest.raises(FactValidationError, match="recorded_at"):
        fact_store.commit_fact_batch(
            FactBatch(
                "earlier",
                [_fact(FACT_2, "new", recorded_at=9, supersedes=FACT_1)],
            )
        )

    fact_store.commit_fact_batch(
        FactBatch(
            "successor",
            [_fact(FACT_2, "new", recorded_at=11, supersedes=FACT_1)],
        )
    )
    with pytest.raises(FactValidationError, match="already has a successor"):
        fact_store.commit_fact_batch(
            FactBatch(
                "second-successor",
                [_fact(FACT_3, "other", recorded_at=12, supersedes=FACT_1)],
            )
        )

    assert fact_store.fact_watermark == 2
