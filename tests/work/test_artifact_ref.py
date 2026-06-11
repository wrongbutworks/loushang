from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def test_artifact_ref_records_actual_artifact_reference_without_product_behavior() -> None:
    from loushang.work import ArtifactRef

    ref = ArtifactRef(
        artifact_id="artifact-1",
        kind="plan",
        uri="docs/plan.md",
        title="Implementation plan",
        domain="coding",
        produced_by_run_id="run-1",
        produced_by_step_id="inspect",
        expected_artifact="implementation-plan",
        media_type="text/markdown",
        metadata={"sha256": "abc123"},
    )

    assert ref.artifact_id == "artifact-1"
    assert ref.kind == "plan"
    assert ref.uri == "docs/plan.md"
    assert ref.title == "Implementation plan"
    assert ref.domain == "coding"
    assert ref.produced_by_run_id == "run-1"
    assert ref.produced_by_step_id == "inspect"
    assert ref.expected_artifact == "implementation-plan"
    assert ref.media_type == "text/markdown"
    assert ref.status == "created"
    assert ref.metadata == {"sha256": "abc123"}
    assert not hasattr(ref, "load")
    assert not hasattr(ref, "render")
    assert not hasattr(ref, "materialize")

    with pytest.raises(FrozenInstanceError):
        ref.status = "updated"  # type: ignore[misc]


def test_artifact_ref_can_represent_planned_or_failed_artifacts_without_uri() -> None:
    from loushang.work import ArtifactRef

    planned = ArtifactRef(
        artifact_id="artifact-planned",
        kind="review",
        expected_artifact="review-notes",
        status="planned",
    )
    failed = ArtifactRef(
        artifact_id="artifact-failed",
        kind="test-report",
        expected_artifact="validation-result",
        status="failed",
        metadata={"reason": "tests failed before report materialized"},
    )

    assert planned.uri is None
    assert planned.status == "planned"
    assert failed.uri is None
    assert failed.status == "failed"
    assert failed.metadata == {"reason": "tests failed before report materialized"}
