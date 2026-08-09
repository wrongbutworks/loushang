from __future__ import annotations

from uuid import UUID

import pytest

from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactRecord,
    LinkAssertion,
    MemoryFactStore,
    ObjectAssertion,
    PropertyAssertion,
    project_facts,
)
from loushang.ontology.query import (
    PropertyFilter,
    QueryBuilder,
    QueryRequest,
    StartFromType,
)
from loushang.ontology.query.engine import execute_query
from loushang.ontology.schema import (
    LinkTypeDefinition,
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    ValueType,
)

SELECTED_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_ID = UUID("00000000-0000-0000-0000-000000000002")
OWNER_ID = UUID("00000000-0000-0000-0000-000000000003")


def _projected_assets():
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.query",
            namespace="urn:test:query",
            version="2.0.0",
            object_types=[
                ObjectTypeDefinition(
                    "Asset",
                    properties=[
                        PropertyDefinition("code", ValueType.STRING, indexed=True),
                        PropertyDefinition("score", ValueType.INTEGER),
                    ],
                ),
                ObjectTypeDefinition(
                    "Owner",
                    properties=[PropertyDefinition("name", ValueType.STRING)],
                ),
            ],
            link_types=[LinkTypeDefinition("owned_by", "Asset", "Owner")],
        )
    )
    records = [
        _fact(1, SELECTED_ID, ObjectAssertion("Asset")),
        _fact(2, SELECTED_ID, PropertyAssertion("code", "A-1")),
        _fact(3, SELECTED_ID, PropertyAssertion("score", 5)),
        _fact(4, OTHER_ID, ObjectAssertion("Asset")),
        _fact(5, OTHER_ID, PropertyAssertion("code", "A-2")),
        _fact(6, OTHER_ID, PropertyAssertion("score", 1)),
        _fact(7, OWNER_ID, ObjectAssertion("Owner")),
        _fact(8, OWNER_ID, PropertyAssertion("name", "Operations")),
        _fact(9, SELECTED_ID, LinkAssertion("owned_by", OWNER_ID)),
    ]
    facts = MemoryFactStore()
    facts.commit_fact_batch(FactBatch("query-fixture", records))
    return project_facts(facts, schema, valid_at=10, recorded_at=10)


def _fact(suffix: int, subject_id: UUID, assertion: object) -> FactRecord:
    return FactRecord(
        fact_id=UUID(f"10000000-0000-0000-0000-{suffix:012d}"),
        subject_id=subject_id,
        assertion=assertion,  # type: ignore[arg-type]
        assertion_kind=AssertionKind.ASSERTED,
        source_ref="source.query-fixture",
        source_record_ref=f"record:{suffix}",
        valid_from=0,
        recorded_at=1,
    )


def test_typed_query_reports_schema_and_projection_freshness() -> None:
    projection = _projected_assets()

    result = execute_query(
        projection.view,
        QueryRequest(
            schema_version="2.0.0",
            steps=(
                StartFromType("Asset"),
                PropertyFilter("score", ">=", 5),
            ),
        ),
    )

    assert result.object_ids == (SELECTED_ID,)
    assert result.schema_version == "2.0.0"
    assert result.projection.fresh is True
    assert result.diagnostics == ()


def test_query_schema_mismatch_is_visible_without_returning_objects() -> None:
    projection = _projected_assets()

    result = execute_query(
        projection.view,
        QueryRequest(
            schema_version="1.0.0",
            steps=(StartFromType("Asset"),),
        ),
    )

    assert result.object_ids == ()
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "schema_version_mismatch"
    ]


def test_query_builder_operates_only_on_a_projection_view() -> None:
    projection = _projected_assets()

    result = (
        QueryBuilder(projection.view)
        .start_from_type("Asset")
        .where("score", ">", 1)
        .execute_result()
    )

    assert result.object_ids == (SELECTED_ID,)
    assert result.projection.fresh is True


def test_query_builder_covers_read_only_traversal_sort_and_window_operations() -> None:
    projection = _projected_assets()
    selected = projection.view.get(SELECTED_ID)
    assert selected is not None

    owners = (
        QueryBuilder(projection.view)
        .start_from(selected)
        .follow("owned_by")
        .where("name", "==", "Operations")
    )
    assert owners.execute_ids() == [OWNER_ID]
    assert owners.execute_count() == 1
    assert owners.execute_exists() is True
    assert owners.execute_first() == projection.view.get(OWNER_ID)

    window = (
        QueryBuilder(projection.view)
        .start_all()
        .where_type("Asset")
        .sort_by("score", ascending=False)
        .offset(1)
        .limit(1)
    )
    assert window.execute_ids() == [OTHER_ID]

    incoming = (
        QueryBuilder(projection.view)
        .start_from(OWNER_ID)
        .follow("owned_by", direction="incoming")
        .execute_ids()
    )
    assert incoming == [SELECTED_ID]
    assert (
        QueryBuilder(projection.view)
        .start_from(SELECTED_ID)
        .as_of(-1)
        .follow("owned_by")
        .execute_ids()
        == []
    )


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [
        ("!=", "A-1", (OTHER_ID,)),
        ("<", 5, (OTHER_ID,)),
        ("<=", 1, (OTHER_ID,)),
        (">", 1, (SELECTED_ID,)),
        (">=", 5, (SELECTED_ID,)),
        ("in", ("A-1",), (SELECTED_ID,)),
        ("contains", "A-", (SELECTED_ID, OTHER_ID)),
    ],
)
def test_query_property_operators(
    operator: str,
    value: object,
    expected: tuple[UUID, ...],
) -> None:
    projection = _projected_assets()
    property_name = "score" if operator in {"<", "<=", ">", ">="} else "code"

    result = execute_query(
        projection.view,
        QueryRequest(
            steps=(
                StartFromType("Asset"),
                PropertyFilter(property_name, operator, value),
            )
        ),
    )

    assert result.object_ids == expected


def test_query_rejects_an_unknown_operator() -> None:
    projection = _projected_assets()

    with pytest.raises(ValueError, match="Unsupported operator"):
        execute_query(
            projection.view,
            QueryRequest(
                steps=(
                    StartFromType("Asset"),
                    PropertyFilter("score", "approximately", 5),
                )
            ),
        )
