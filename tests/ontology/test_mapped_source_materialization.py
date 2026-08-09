from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from loushang.ontology.facts import (
    AssertionKind,
    FactBatch,
    FactRecord,
    ObjectAssertion,
    PropertyAssertion,
)
from loushang.ontology.projection import (
    FactOrigin,
    ProjectionFreshnessStatus,
    ProjectionMaterializationError,
    SchemaDefaultOrigin,
    SourceOrigin,
    evaluate_projection_freshness,
    materialize_projection,
)
from loushang.ontology.schema import (
    ObjectTypeDefinition,
    OntologyCompiler,
    OntologyPackageDraft,
    PropertyDefinition,
    StateAuthority,
    ValueType,
)
from loushang.ontology.source import (
    MappedSourceInput,
    MappedSourceObject,
    MappedSourceProperty,
    MappedSourceSnapshot,
    SourceBinding,
    SourceInputRevision,
)
from loushang.ontology.storage import (
    MemoryFactStore,
    MemoryProjectionStore,
    SQLiteProjectionStore,
)

ASSET_ID = UUID("00000000-0000-0000-0000-000000000001")
REVIEW_FACT_ID = UUID("10000000-0000-0000-0000-000000000001")


def _schema():
    return OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.mapped-source",
            namespace="urn:test:mapped-source",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    "Asset",
                    semantic_id="asset",
                    state_authority=StateAuthority.SOURCE_BACKED,
                    properties=[
                        PropertyDefinition(
                            "code",
                            ValueType.STRING,
                            semantic_id="asset.code",
                            state_authority=StateAuthority.SOURCE_BACKED,
                            required=True,
                        ),
                        PropertyDefinition(
                            "review_status",
                            ValueType.STRING,
                            semantic_id="asset.review-status",
                            state_authority=StateAuthority.ONTOLOGY_OWNED,
                            required=True,
                        ),
                        PropertyDefinition(
                            "risk",
                            ValueType.STRING,
                            semantic_id="asset.risk",
                            state_authority=StateAuthority.ONTOLOGY_OWNED,
                            default="unreviewed",
                        ),
                    ],
                )
            ],
        )
    )


def _selection():
    facts = MemoryFactStore()
    facts.commit_fact_batch(
        FactBatch(
            "review",
            [
                FactRecord(
                    fact_id=REVIEW_FACT_ID,
                    subject_id=ASSET_ID,
                    assertion=PropertyAssertion("review_status", "approved"),
                    assertion_kind=AssertionKind.ASSERTED,
                    source_ref="review.office",
                    source_record_ref="approval:17",
                    valid_from=5,
                    recorded_at=8,
                    author_ref="user:123",
                )
            ],
        )
    )
    return facts.select_facts(valid_at=10, recorded_at=10)


def _binding(*, binding_id: str = "erp.assets") -> SourceBinding:
    return SourceBinding(
        binding_id=binding_id,
        mapping_version="mapping-v3",
        object_existence_ids=("asset",),
        property_ids=("asset.code",),
    )


def _source_input(*, binding_id: str = "erp.assets") -> MappedSourceInput:
    return MappedSourceInput(
        binding_id=binding_id,
        mapping_version="mapping-v3",
        source_revision="erp-42",
        payload=MappedSourceSnapshot(
            objects=(
                MappedSourceObject(
                    object_id=ASSET_ID,
                    object_type_id="asset",
                    source_record_ref="asset:A-1",
                    properties=(
                        MappedSourceProperty(
                            property_id="asset.code",
                            value="A-1",
                            field_ref="assets.asset_code",
                            valid_from=1,
                        ),
                    ),
                ),
            )
        ),
    )


def test_memory_slice_combines_source_fact_and_default_with_exact_origins() -> None:
    schema = _schema()
    snapshot = materialize_projection(
        _selection(),
        schema,
        source_bindings=(_binding(),),
        source_inputs=(_source_input(),),
        built_at=11,
    )
    installed = MemoryProjectionStore()
    installed.replace(snapshot)

    asset = installed.get(ASSET_ID)
    assert asset is not None
    assert asset.get("code") == "A-1"
    assert asset.get("review_status") == "approved"
    assert asset.get("risk") == "unreviewed"
    assert asset.property("code").origin == SourceOrigin(  # type: ignore[union-attr]
        binding_id="erp.assets",
        mapping_version="mapping-v3",
        source_revision="erp-42",
        source_record_ref="asset:A-1",
        field_ref="assets.asset_code",
    )
    assert asset.property("review_status").origin == FactOrigin(  # type: ignore[union-attr]
        REVIEW_FACT_ID
    )
    assert asset.property("risk").origin == SchemaDefaultOrigin(  # type: ignore[union-attr]
        snapshot.state.schema_identity
    )
    assert snapshot.state.materialization_cut.source_inputs == (
        SourceInputRevision("erp.assets", "mapping-v3", "erp-42"),
    )
    assert snapshot.state.materialization_cut.fact_watermark == 1
    assert snapshot.state.materialization_cut.valid_at == 10
    assert snapshot.state.materialization_cut.recorded_at == 10


def test_mapped_source_values_are_detached_and_materialization_is_deterministic() -> (
    None
):
    mutable_value = {"labels": ["critical"]}
    source_property = MappedSourceProperty(
        property_id="asset.code",
        value=mutable_value,
        field_ref="assets.asset_code",
        valid_from=1,
    )
    mutable_value["labels"].append("changed")

    assert source_property.raw_value == {"labels": ["critical"]}
    with pytest.raises(AttributeError):
        source_property.property_id = "changed"  # type: ignore[misc]

    first = materialize_projection(
        _selection(),
        _schema(),
        source_bindings=(_binding(),),
        source_inputs=(_source_input(),),
    )
    second = materialize_projection(
        _selection(),
        _schema(),
        source_bindings=tuple(reversed((_binding(),))),
        source_inputs=tuple(reversed((_source_input(),))),
    )
    assert first == second


def test_ambiguous_source_authority_fails_instead_of_using_input_order() -> None:
    with pytest.raises(ProjectionMaterializationError) as exc_info:
        materialize_projection(
            _selection(),
            _schema(),
            source_bindings=(
                _binding(binding_id="erp.assets"),
                _binding(binding_id="crm.assets"),
            ),
            source_inputs=(
                _source_input(binding_id="erp.assets"),
                _source_input(binding_id="crm.assets"),
            ),
        )

    assert "source_authority_binding_conflict" in {
        item.code for item in exc_info.value.diagnostics
    }


def test_source_freshness_is_explicit_and_does_not_mutate_the_cut() -> None:
    state = materialize_projection(
        _selection(),
        _schema(),
        source_bindings=(_binding(),),
        source_inputs=(_source_input(),),
    ).state
    cut = state.materialization_cut

    unknown = evaluate_projection_freshness(
        state,
        observed_fact_watermark=1,
        observed_source_heads=None,
        observed_at=20,
    )
    current = evaluate_projection_freshness(
        state,
        observed_fact_watermark=1,
        observed_source_heads=(
            SourceInputRevision("erp.assets", "mapping-v3", "erp-42"),
        ),
        observed_at=21,
    )
    stale = evaluate_projection_freshness(
        state,
        observed_fact_watermark=1,
        observed_source_heads=(
            SourceInputRevision("erp.assets", "mapping-v3", "erp-43"),
        ),
        observed_at=22,
    )

    assert unknown.status is ProjectionFreshnessStatus.UNKNOWN
    assert current.status is ProjectionFreshnessStatus.CURRENT
    assert stale.status is ProjectionFreshnessStatus.STALE
    assert state.materialization_cut is cut
    assert cut.source_inputs[0].source_revision == "erp-42"


def test_sqlite_v2_rejects_source_lineage_instead_of_losing_it(
    tmp_path: Path,
) -> None:
    snapshot = materialize_projection(
        _selection(),
        _schema(),
        source_bindings=(_binding(),),
        source_inputs=(_source_input(),),
    )
    store = SQLiteProjectionStore(tmp_path / "ontology.sqlite3")
    try:
        with pytest.raises(ValueError, match="SQLite v2 cannot store mapped-source"):
            store.replace(snapshot)
    finally:
        store.close()


def test_transient_derived_values_wait_for_a_computation_origin() -> None:
    schema = OntologyCompiler().compile(
        OntologyPackageDraft(
            package_id="test.derived-cut",
            namespace="urn:test:derived-cut",
            version="1.0.0",
            object_types=[
                ObjectTypeDefinition(
                    "Asset",
                    semantic_id="asset",
                    state_authority=StateAuthority.ONTOLOGY_OWNED,
                    properties=[
                        PropertyDefinition(
                            "score",
                            ValueType.INTEGER,
                            semantic_id="asset.score",
                            state_authority=StateAuthority.DERIVED,
                            default=0,
                        )
                    ],
                )
            ],
        )
    )
    facts = MemoryFactStore()
    facts.commit_fact_batch(
        FactBatch(
            "asset",
            [
                FactRecord(
                    fact_id=REVIEW_FACT_ID,
                    subject_id=ASSET_ID,
                    assertion=ObjectAssertion("Asset"),
                    assertion_kind=AssertionKind.ASSERTED,
                    source_ref="test",
                    source_record_ref="asset:A-1",
                    valid_from=0,
                    recorded_at=1,
                )
            ],
        )
    )

    with pytest.raises(ProjectionMaterializationError) as exc_info:
        materialize_projection(
            facts.select_facts(valid_at=2, recorded_at=2),
            schema,
        )

    assert {item.code for item in exc_info.value.diagnostics} == {
        "derived_state_unsupported"
    }
