from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactProjectionError,
    FactRecord,
    LinkAssertion,
    MemoryFactStore,
    ObjectAssertion,
    PropertyAssertion,
    project_facts,
)
from loushang.ontology.schema import (
    LinkCardinality,
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    ValueType,
)

ASSET_ID = UUID("00000000-0000-0000-0000-000000000001")
OWNER_ID = UUID("00000000-0000-0000-0000-000000000002")


def _schema():
    return OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.fact-projection",
            namespace="urn:test:fact-projection",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    "Asset",
                    properties=[
                        PropertyDefinition("code", ValueType.STRING, required=True, unique=True),
                        PropertyDefinition("score", ValueType.INTEGER),
                        PropertyDefinition("observed_at", ValueType.DATETIME),
                    ],
                ),
                ObjectTypeDefinition("Owner"),
            ],
            link_types=[
                LinkTypeDefinition(
                    "owned_by",
                    "Asset",
                    "Owner",
                    cardinality=LinkCardinality.MANY_TO_ONE,
                )
            ],
        )
    )


def _fact(
    suffix: int,
    subject_id: UUID,
    assertion: object,
    *,
    source_ref: str = "source.erp",
    source_record_ref: str | None = None,
    recorded_at: float = 10.0,
) -> FactRecord:
    return FactRecord(
        fact_id=UUID(f"10000000-0000-0000-0000-{suffix:012d}"),
        subject_id=subject_id,
        assertion=assertion,  # type: ignore[arg-type]
        assertion_kind=AssertionKind.ASSERTED,
        source_ref=source_ref,
        source_record_ref=source_record_ref or f"record:{suffix}",
        valid_from=0,
        recorded_at=recorded_at,
    )


def _complete_facts() -> list[FactRecord]:
    return [
        _fact(1, ASSET_ID, ObjectAssertion("Asset")),
        _fact(2, ASSET_ID, PropertyAssertion("code", "A-1")),
        _fact(3, ASSET_ID, PropertyAssertion("score", 7)),
        _fact(4, ASSET_ID, PropertyAssertion("observed_at", "2026-08-09T00:00:00+00:00")),
        _fact(5, OWNER_ID, ObjectAssertion("Owner")),
        _fact(6, ASSET_ID, LinkAssertion("owned_by", OWNER_ID, {"source": "erp"})),
    ]


def test_fact_projection_materializes_schema_valid_objects_properties_and_links() -> None:
    facts = MemoryFactStore()
    facts.commit_fact_batch(FactBatch("complete", _complete_facts()))

    projection = project_facts(facts, _schema(), valid_at=20.0, recorded_at=20.0)

    asset = projection.view.get(ASSET_ID)
    owner = projection.view.get(OWNER_ID)
    assert asset is not None
    assert owner is not None
    assert asset.get("code") == "A-1"
    assert asset.get("score") == 7
    assert asset.get("observed_at") == datetime(2026, 8, 9, tzinfo=UTC)
    assert projection.view.find_neighbors(ASSET_ID, "owned_by") == [owner]
    assert projection.source_fact_watermark == 6
    assert projection.schema_version == "1.0.0"
    assert projection.valid_at == 20.0
    assert projection.recorded_at == 20.0
    assert projection.fact_ids == tuple(item.fact_id for item in _complete_facts())
    assert asset.history("code")[0].timestamp == 0.0
    assert not hasattr(projection.view, "create")
    assert not hasattr(projection.view, "set_property")
    assert not hasattr(projection.view, "link_objects")

    with pytest.raises(RuntimeError, match="read-only"):
        asset.set("score", 8)
    with pytest.raises(RuntimeError, match="read-only"):
        asset.link("owned_by", owner)
    with pytest.raises(RuntimeError, match="read-only"):
        asset.unlink("owned_by", owner)
    assert asset.get("score") == 7


def test_projection_is_deterministic_for_equivalent_fact_content() -> None:
    facts = _complete_facts()
    first = MemoryFactStore()
    second = MemoryFactStore()
    first.commit_fact_batch(FactBatch("one", facts))
    second.commit_fact_batch(FactBatch("two", list(reversed(facts))))

    projected_first = project_facts(first, _schema(), valid_at=20, recorded_at=20)
    projected_second = project_facts(second, _schema(), valid_at=20, recorded_at=20)

    assert [obj.to_dict() for obj in projected_first.view.all_objects()] == [
        obj.to_dict() for obj in projected_second.view.all_objects()
    ]


def test_projection_rejects_cross_source_value_conflict_instead_of_picking_winner() -> None:
    facts = MemoryFactStore()
    records = _complete_facts()
    records.append(
        _fact(
            7,
            ASSET_ID,
            PropertyAssertion("score", 9),
            source_ref="source.other",
        )
    )
    facts.commit_fact_batch(FactBatch("conflict", records))

    with pytest.raises(FactProjectionError, match="conflicting property") as exc_info:
        project_facts(facts, _schema(), valid_at=20, recorded_at=20)

    assert exc_info.value.diagnostics[0].code == "property_fact_conflict"


def test_projection_rejects_missing_required_property_and_unknown_endpoint() -> None:
    missing = MemoryFactStore()
    missing.commit_fact_batch(
        FactBatch("missing", [_fact(1, ASSET_ID, ObjectAssertion("Asset"))])
    )
    with pytest.raises(FactProjectionError, match="code"):
        project_facts(missing, _schema(), valid_at=20, recorded_at=20)

    endpoint = MemoryFactStore()
    endpoint.commit_fact_batch(
        FactBatch(
            "endpoint",
            [
                _fact(1, ASSET_ID, ObjectAssertion("Asset")),
                _fact(2, ASSET_ID, PropertyAssertion("code", "A-1")),
                _fact(3, ASSET_ID, LinkAssertion("owned_by", OWNER_ID)),
            ],
        )
    )
    with pytest.raises(FactProjectionError, match="target"):
        project_facts(endpoint, _schema(), valid_at=20, recorded_at=20)


def test_projection_reports_object_type_and_property_shape_conflicts() -> None:
    facts = MemoryFactStore()
    facts.commit_fact_batch(
        FactBatch(
            "shape",
            [
                _fact(1, ASSET_ID, ObjectAssertion("Asset")),
                _fact(
                    2,
                    ASSET_ID,
                    ObjectAssertion("Owner"),
                    source_ref="source.other",
                ),
                _fact(3, OWNER_ID, ObjectAssertion("Unknown")),
                _fact(4, UUID(int=99), PropertyAssertion("code", "orphan")),
            ],
        )
    )

    with pytest.raises(FactProjectionError) as exc_info:
        project_facts(facts, _schema(), valid_at=20, recorded_at=20)

    assert {item.code for item in exc_info.value.diagnostics} == {
        "object_type_fact_conflict",
        "property_subject_missing",
        "unknown_object_type",
    }


def test_projection_reports_unknown_property_and_invalid_datetime_value() -> None:
    facts = MemoryFactStore()
    facts.commit_fact_batch(
        FactBatch(
            "properties",
            [
                _fact(1, ASSET_ID, ObjectAssertion("Asset")),
                _fact(2, ASSET_ID, PropertyAssertion("code", "A-1")),
                _fact(3, ASSET_ID, PropertyAssertion("unknown", 1)),
                _fact(4, ASSET_ID, PropertyAssertion("observed_at", "not-a-date")),
            ],
        )
    )

    with pytest.raises(FactProjectionError) as exc_info:
        project_facts(facts, _schema(), valid_at=20, recorded_at=20)

    assert {item.code for item in exc_info.value.diagnostics} == {
        "property_fact_value_invalid",
        "unknown_property",
    }


def test_projection_reports_unknown_link_endpoint_type_and_link_payload_conflict() -> None:
    facts = MemoryFactStore()
    facts.commit_fact_batch(
        FactBatch(
            "links",
            [
                _fact(1, ASSET_ID, ObjectAssertion("Asset")),
                _fact(2, ASSET_ID, PropertyAssertion("code", "A-1")),
                _fact(3, OWNER_ID, ObjectAssertion("Asset")),
                _fact(4, OWNER_ID, PropertyAssertion("code", "A-2")),
                _fact(5, ASSET_ID, LinkAssertion("unknown", OWNER_ID)),
                _fact(6, ASSET_ID, LinkAssertion("owned_by", OWNER_ID)),
            ],
        )
    )

    with pytest.raises(FactProjectionError) as exc_info:
        project_facts(facts, _schema(), valid_at=20, recorded_at=20)

    assert {item.code for item in exc_info.value.diagnostics} == {
        "link_endpoint_type_invalid",
        "unknown_link_type",
    }

    conflicting = MemoryFactStore()
    records = _complete_facts()
    records.append(
        _fact(
            7,
            ASSET_ID,
            LinkAssertion("owned_by", OWNER_ID, {"source": "other"}),
            source_ref="source.other",
        )
    )
    conflicting.commit_fact_batch(FactBatch("link-conflict", records))
    with pytest.raises(FactProjectionError) as conflict_info:
        project_facts(conflicting, _schema(), valid_at=20, recorded_at=20)
    assert conflict_info.value.diagnostics[0].code == "link_fact_conflict"


def test_projection_runs_required_link_integrity_after_materialization() -> None:
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.required-fact-link",
            namespace="urn:test:required-fact-link",
            version="1.0.0",
            object_types=[ObjectTypeDefinition("Source"), ObjectTypeDefinition("Target")],
            link_types=[LinkTypeDefinition("target", "Source", "Target", required=True)],
        )
    )
    facts = MemoryFactStore()
    facts.commit_fact_batch(
        FactBatch("required", [_fact(1, ASSET_ID, ObjectAssertion("Source"))])
    )

    with pytest.raises(FactProjectionError) as exc_info:
        project_facts(facts, schema, valid_at=20, recorded_at=20)

    assert exc_info.value.diagnostics[0].code == "required_link_missing"
