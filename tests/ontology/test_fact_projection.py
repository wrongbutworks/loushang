from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactRecord,
    LinkAssertion,
    ObjectAssertion,
    PropertyAssertion,
)
from loushang.ontology.projection import (
    ProjectionMaterializationError,
    materialize_projection,
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
from loushang.ontology.storage import MemoryFactStore

ASSET_ID = UUID("00000000-0000-0000-0000-000000000001")
OWNER_ID = UUID("00000000-0000-0000-0000-000000000002")
OTHER_ID = UUID("00000000-0000-0000-0000-000000000003")


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
                        PropertyDefinition(
                            "code",
                            ValueType.STRING,
                            required=True,
                            unique=True,
                        ),
                        PropertyDefinition("score", ValueType.INTEGER),
                        PropertyDefinition("observed_at", ValueType.DATETIME),
                        PropertyDefinition("payload", ValueType.JSON),
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
    recorded_at: float = 10.0,
) -> FactRecord:
    return FactRecord(
        fact_id=UUID(f"10000000-0000-0000-0000-{suffix:012d}"),
        subject_id=subject_id,
        assertion=assertion,  # type: ignore[arg-type]
        assertion_kind=AssertionKind.ASSERTED,
        source_ref=source_ref,
        source_record_ref=f"record:{suffix}",
        valid_from=0,
        recorded_at=recorded_at,
    )


def _complete_facts() -> list[FactRecord]:
    return [
        _fact(1, ASSET_ID, ObjectAssertion("Asset")),
        _fact(2, ASSET_ID, PropertyAssertion("code", "A-1")),
        _fact(3, ASSET_ID, PropertyAssertion("score", 7)),
        _fact(
            4,
            ASSET_ID,
            PropertyAssertion("observed_at", "2026-08-09T00:00:00+00:00"),
        ),
        _fact(5, OWNER_ID, ObjectAssertion("Owner")),
        _fact(6, ASSET_ID, LinkAssertion("owned_by", OWNER_ID, {"source": "erp"})),
    ]


def _materialize(records: list[FactRecord], *, schema=None):
    store = MemoryFactStore()
    store.commit_fact_batch(FactBatch("fixture", records))
    return materialize_projection(
        store,
        _schema() if schema is None else schema,
        valid_at=20,
        recorded_at=20,
    )


def test_materializer_builds_an_immutable_reproducible_snapshot() -> None:
    snapshot = _materialize(_complete_facts())

    asset = snapshot.get(ASSET_ID)
    owner = snapshot.get(OWNER_ID)
    assert asset is not None
    assert owner is not None
    assert asset.get("code") == "A-1"
    assert asset.get("score") == 7
    assert asset.get("observed_at") == datetime(2026, 8, 9, tzinfo=UTC)
    assert snapshot.find_neighbors(ASSET_ID, "owned_by") == (owner,)
    assert snapshot.state.source_fact_watermark == 6
    assert snapshot.state.projected_fact_watermark == 6
    assert snapshot.state.fresh is True
    assert snapshot.state.schema_version == "1.0.0"
    assert snapshot.state.valid_at == 20
    assert snapshot.state.recorded_at == 20
    assert snapshot.fact_ids == tuple(item.fact_id for item in _complete_facts())
    assert asset.property("code").valid_from == 0  # type: ignore[union-attr]
    assert not hasattr(asset, "set")
    assert not hasattr(snapshot, "create")
    with pytest.raises(FrozenInstanceError):
        asset.object_type = "Changed"  # type: ignore[misc]


def test_projection_json_values_are_detached_and_deterministic() -> None:
    records = _complete_facts()
    records.append(_fact(7, ASSET_ID, PropertyAssertion("payload", {"items": [1]})))
    first = _materialize(records)
    second = _materialize(list(reversed(records)))

    first_asset = first.get(ASSET_ID)
    assert first_asset is not None
    exposed = first_asset.get("payload")
    assert isinstance(exposed, dict)
    exposed["items"].append(2)  # type: ignore[union-attr]
    assert first_asset.get("payload") == {"items": [1]}
    assert first.objects == second.objects
    assert first.links == second.links


def test_projection_rejects_conflicting_or_orphaned_facts() -> None:
    records = _complete_facts()
    records.append(
        _fact(
            7,
            ASSET_ID,
            PropertyAssertion("score", 9),
            source_ref="source.other",
        )
    )
    with pytest.raises(ProjectionMaterializationError) as conflict:
        _materialize(records)
    assert "property_fact_conflict" in {
        item.code for item in conflict.value.diagnostics
    }

    with pytest.raises(ProjectionMaterializationError) as orphan:
        _materialize([_fact(1, ASSET_ID, PropertyAssertion("score", 1))])
    assert {item.code for item in orphan.value.diagnostics} == {
        "property_subject_missing"
    }


def test_projection_reports_shape_property_and_endpoint_failures_together() -> None:
    records = [
        _fact(1, ASSET_ID, ObjectAssertion("Asset")),
        _fact(2, ASSET_ID, ObjectAssertion("Owner"), source_ref="source.other"),
        _fact(3, OWNER_ID, ObjectAssertion("Unknown")),
        _fact(4, OTHER_ID, PropertyAssertion("orphan", 1)),
        _fact(5, ASSET_ID, LinkAssertion("unknown", OWNER_ID)),
    ]
    with pytest.raises(ProjectionMaterializationError) as exc_info:
        _materialize(records)

    assert {item.code for item in exc_info.value.diagnostics} == {
        "link_endpoint_missing",
        "object_type_fact_conflict",
        "property_subject_missing",
        "unknown_object_type",
    }


@pytest.mark.parametrize(
    ("definition", "value"),
    [
        (PropertyDefinition("value", ValueType.STRING), 1),
        (PropertyDefinition("value", ValueType.INTEGER), True),
        (PropertyDefinition("value", ValueType.NUMBER), "1"),
        (PropertyDefinition("value", ValueType.BOOLEAN), 1),
        (PropertyDefinition("value", ValueType.DATETIME), "not-a-date"),
    ],
)
def test_projection_validates_schema_value_types(
    definition: PropertyDefinition,
    value: object,
) -> None:
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.values",
            namespace="urn:test:values",
            version="1.0.0",
            object_types=[ObjectTypeDefinition("Value", properties=[definition])],
        )
    )
    records = [
        _fact(1, ASSET_ID, ObjectAssertion("Value")),
        _fact(2, ASSET_ID, PropertyAssertion("value", value)),
    ]

    with pytest.raises(ProjectionMaterializationError) as exc_info:
        _materialize(records, schema=schema)

    assert exc_info.value.diagnostics[0].code == "property_fact_value_invalid"


def test_projection_enforces_required_unique_abstract_and_inherited_properties() -> (
    None
):
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.integrity",
            namespace="urn:test:integrity",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    "Base",
                    properties=[
                        PropertyDefinition(
                            "code",
                            ValueType.STRING,
                            required=True,
                            unique=True,
                        )
                    ],
                    abstract=True,
                ),
                ObjectTypeDefinition("Asset", parent_types=["Base"]),
            ],
        )
    )
    records = [
        _fact(1, ASSET_ID, ObjectAssertion("Asset")),
        _fact(2, OWNER_ID, ObjectAssertion("Asset")),
        _fact(3, ASSET_ID, PropertyAssertion("code", "same")),
        _fact(4, OWNER_ID, PropertyAssertion("code", "same")),
        _fact(5, OTHER_ID, ObjectAssertion("Base")),
    ]

    with pytest.raises(ProjectionMaterializationError) as exc_info:
        _materialize(records, schema=schema)

    assert {item.code for item in exc_info.value.diagnostics} == {
        "abstract_object_type",
        "unique_property_conflict",
    }


@pytest.mark.parametrize(
    ("cardinality", "second_source", "second_target", "should_fail"),
    [
        (LinkCardinality.ONE_TO_ONE, True, False, True),
        (LinkCardinality.ONE_TO_MANY, True, False, True),
        (LinkCardinality.MANY_TO_ONE, False, True, True),
        (LinkCardinality.MANY_TO_MANY, True, True, False),
    ],
)
def test_projection_enforces_link_cardinality(
    cardinality: LinkCardinality,
    second_source: bool,
    second_target: bool,
    should_fail: bool,
) -> None:
    target_2 = UUID("00000000-0000-0000-0000-000000000004")
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.cardinality",
            namespace="urn:test:cardinality",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition("Source"),
                ObjectTypeDefinition("Target"),
            ],
            link_types=[LinkTypeDefinition("relates", "Source", "Target", cardinality)],
        )
    )
    records = [
        _fact(1, ASSET_ID, ObjectAssertion("Source")),
        _fact(2, OTHER_ID, ObjectAssertion("Source")),
        _fact(3, OWNER_ID, ObjectAssertion("Target")),
        _fact(4, target_2, ObjectAssertion("Target")),
        _fact(5, ASSET_ID, LinkAssertion("relates", OWNER_ID)),
    ]
    if second_source:
        records.append(_fact(6, OTHER_ID, LinkAssertion("relates", OWNER_ID)))
    if second_target:
        records.append(_fact(7, ASSET_ID, LinkAssertion("relates", target_2)))

    if should_fail:
        with pytest.raises(ProjectionMaterializationError) as exc_info:
            _materialize(records, schema=schema)
        assert exc_info.value.diagnostics[0].code == "link_cardinality_violation"
    else:
        assert len(_materialize(records, schema=schema).links) == 3


def test_projection_enforces_required_links() -> None:
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.required-link",
            namespace="urn:test:required-link",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition("Source"),
                ObjectTypeDefinition("Target"),
            ],
            link_types=[
                LinkTypeDefinition("target", "Source", "Target", required=True)
            ],
        )
    )

    with pytest.raises(ProjectionMaterializationError) as exc_info:
        _materialize(
            [_fact(1, ASSET_ID, ObjectAssertion("Source"))],
            schema=schema,
        )

    assert exc_info.value.diagnostics[0].code == "required_link_missing"
