from __future__ import annotations

from uuid import UUID

import pytest

from loushang.ontology import (
    FactBatch as PublicFactBatch,
)
from loushang.ontology import (
    FactRecord as PublicFactRecord,
)
from loushang.ontology import (
    ObjectAssertion as PublicObjectAssertion,
)
from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactRecord,
    FactValidationError,
    LinkAssertion,
    ObjectAssertion,
    PropertyAssertion,
)

SUBJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
TARGET_ID = UUID("00000000-0000-0000-0000-000000000002")


def _fact(**overrides: object) -> FactRecord:
    values: dict[str, object] = {
        "fact_id": UUID("10000000-0000-0000-0000-000000000001"),
        "subject_id": SUBJECT_ID,
        "assertion": PropertyAssertion("payload", {"items": [1, None]}),
        "assertion_kind": AssertionKind.ASSERTED,
        "source_ref": "source.erp",
        "source_record_ref": "asset:A-1",
        "valid_from": 10.0,
        "recorded_at": 20.0,
    }
    values.update(overrides)
    return FactRecord(**values)  # type: ignore[arg-type]


def test_typed_assertions_preserve_json_null_and_isolate_mutable_values() -> None:
    value = {"items": [1, None]}
    assertion = PropertyAssertion("payload", value)
    link_properties = {"roles": ["owner"]}
    link = LinkAssertion("owned_by", TARGET_ID, link_properties)
    value["items"].append(2)
    link_properties["roles"].append("changed")

    assert assertion.value == {"items": [1, None]}
    assert link.properties == {"roles": ["owner"]}
    exposed = assertion.value
    assert isinstance(exposed, dict)
    exposed["changed"] = True
    assert assertion.value == {"items": [1, None]}
    assert ObjectAssertion("Asset").object_type == "Asset"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"source_ref": ""}, "source_ref"),
        ({"source_record_ref": "  "}, "source_record_ref"),
        ({"valid_from": float("nan")}, "valid_from"),
        ({"valid_to": 10.0}, "valid_to"),
        ({"recorded_at": float("inf")}, "recorded_at"),
        ({"confidence": -0.1}, "confidence"),
        ({"confidence": 1.1}, "confidence"),
        ({"evidence_refs": ["ok", ""]}, "evidence_refs"),
        ({"supersedes": UUID("10000000-0000-0000-0000-000000000001")}, "itself"),
        (
            {
                "supersedes": UUID("10000000-0000-0000-0000-000000000002"),
                "corrects": UUID("10000000-0000-0000-0000-000000000003"),
            },
            "at most one",
        ),
    ],
)
def test_fact_envelope_rejects_invalid_provenance_and_time(
    overrides: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(FactValidationError, match=error):
        _fact(**overrides)


def test_fact_and_batch_have_canonical_round_trip() -> None:
    fact = _fact(
        valid_to=30.0,
        evidence_refs=["evidence:1"],
        methodology_ref="method:1",
        author_ref="user:1",
        confidence=0.9,
    )
    batch = FactBatch("batch-1", [fact])

    restored = FactBatch.from_json(batch.to_json())

    assert restored == batch
    assert restored.facts == (fact,)


@pytest.mark.parametrize(
    ("assertion", "category", "predicate"),
    [
        (ObjectAssertion("Asset"), "object", "$type"),
        (PropertyAssertion("status", None), "property", "status"),
        (LinkAssertion("owned_by", TARGET_ID, {"role": "owner"}), "link", "owned_by"),
    ],
)
def test_every_assertion_kind_round_trips_with_stable_coordinate(
    assertion: object,
    category: str,
    predicate: str,
) -> None:
    fact = _fact(assertion=assertion)

    restored = FactRecord.from_json(fact.to_json())

    assert restored == fact
    assert restored.assertion_category == category
    assert restored.predicate == predicate


def test_fact_values_reject_non_json_content_and_invalid_documents() -> None:
    with pytest.raises(FactValidationError, match="JSON-safe"):
        PropertyAssertion("payload", (1, 2))
    with pytest.raises(FactValidationError, match="JSON object"):
        LinkAssertion("owned_by", TARGET_ID, ["not", "an", "object"])
    with pytest.raises(FactValidationError, match="fact JSON"):
        FactRecord.from_json("{not-json")
    with pytest.raises(FactValidationError, match="batch"):
        FactBatch.from_json("{}")


def test_fact_batch_rejects_empty_or_duplicate_content() -> None:
    fact = _fact()
    with pytest.raises(FactValidationError, match="batch_id"):
        FactBatch("", [fact])
    with pytest.raises(FactValidationError, match="at least one"):
        FactBatch("batch", [])
    with pytest.raises(FactValidationError, match="duplicate fact_id"):
        FactBatch("batch", [fact, fact])


def test_common_fact_values_are_reexported_by_the_ontology_package() -> None:
    assert PublicFactBatch is FactBatch
    assert PublicFactRecord is FactRecord
    assert PublicObjectAssertion is ObjectAssertion
