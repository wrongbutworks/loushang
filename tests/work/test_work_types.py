from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest


def test_work_operation_keeps_json_compatible_payload_and_source_defaults() -> None:
    from loushang.work import WorkOperation

    operation = WorkOperation(
        operation_id="op-1",
        kind="SubmitCodingTurn",
        session_id=None,
        domain="coding",
        payload={"text": "fix this bug"},
    )

    assert operation.operation_id == "op-1"
    assert operation.kind == "SubmitCodingTurn"
    assert operation.session_id is None
    assert operation.domain == "coding"
    assert operation.payload == {"text": "fix this bug"}
    assert operation.source == {}

    with pytest.raises(FrozenInstanceError):
        operation.domain = "research"  # type: ignore[misc]


def test_work_run_tracks_p0_single_turn_metadata_without_multi_agent_surface() -> None:
    from loushang.work import WorkRun

    run = WorkRun(
        run_id="run-1",
        operation_id="op-1",
        session_id="session-1",
        domain="coding",
        status="accepted",
    )

    assert run.run_id == "run-1"
    assert run.operation_id == "op-1"
    assert run.session_id == "session-1"
    assert run.domain == "coding"
    assert run.status == "accepted"
    assert run.method_id is None
    assert run.plan_id is None
    assert run.current_step_id is None
    assert not hasattr(run, "agent_lane")
    assert not hasattr(run, "task_ledger")
    assert not hasattr(run, "collaboration_bus")


def test_work_run_tracks_plan_and_current_step_metadata_without_multi_agent_surface() -> None:
    from loushang.work import WorkRun

    run = WorkRun(
        run_id="run-1",
        operation_id="op-1",
        session_id="session-1",
        domain="coding",
        status="running",
        method_id="method:task:review",
        plan_id="plan:method:task:review",
        current_step_id="inspect",
    )

    assert run.method_id == "method:task:review"
    assert run.plan_id == "plan:method:task:review"
    assert run.current_step_id == "inspect"
    assert not hasattr(run, "agent_lane")
    assert not hasattr(run, "task_ledger")
    assert not hasattr(run, "collaboration_bus")


def test_work_step_run_tracks_step_lifecycle_metadata() -> None:
    from loushang.work import WorkStepDeviation, WorkStepRun

    deviation = WorkStepDeviation(
        step_id="inspect",
        deviation_type="adapted",
        reason="Repository state made the default inspection path too broad.",
        policy_level="reasoned",
        evidence_refs=("changed-files",),
        risk="low",
        outcome="accepted",
    )

    step_run = WorkStepRun(
        run_id="run-1",
        plan_id="plan:method:task:review",
        step_id="inspect",
        sequence=1,
        status="running",
        method_id="method:task:review",
        title="Inspect current changes",
        phase="EXPLORE",
        role="EXPLORER",
        expected_artifacts=("review-notes",),
        success_criteria=("Changed files are understood",),
        deviation=deviation,
        metadata={"step_index": 0},
    )

    assert step_run.run_id == "run-1"
    assert step_run.plan_id == "plan:method:task:review"
    assert step_run.step_id == "inspect"
    assert step_run.sequence == 1
    assert step_run.status == "running"
    assert step_run.method_id == "method:task:review"
    assert step_run.title == "Inspect current changes"
    assert step_run.phase == "EXPLORE"
    assert step_run.activity is None
    assert step_run.task is None
    assert step_run.role == "EXPLORER"
    assert step_run.expected_artifacts == ("review-notes",)
    assert step_run.success_criteria == ("Changed files are understood",)
    assert step_run.deviation == deviation
    assert deviation.step_id == "inspect"
    assert deviation.deviation_type == "adapted"
    assert deviation.reason == "Repository state made the default inspection path too broad."
    assert deviation.policy_level == "reasoned"
    assert deviation.evidence_refs == ("changed-files",)
    assert deviation.approval_ref is None
    assert deviation.risk == "low"
    assert deviation.outcome == "accepted"
    assert step_run.metadata == {"step_index": 0}

    with pytest.raises(FrozenInstanceError):
        step_run.status = "completed"  # type: ignore[misc]


def test_work_event_carries_delivery_hint_and_optional_source_event_ref() -> None:
    from loushang.work import WorkEvent

    created_at = datetime(2026, 6, 1, 10, 30, tzinfo=UTC)
    event = WorkEvent(
        event_id="event-1",
        kind="ContentDelta",
        run_id="run-1",
        session_id="session-1",
        domain="coding",
        operation_id="op-1",
        sequence=1,
        created_at=created_at,
        delivery_hint="coalesce",
        payload={"text": "hello"},
    )

    assert event.event_id == "event-1"
    assert event.kind == "ContentDelta"
    assert event.run_id == "run-1"
    assert event.session_id == "session-1"
    assert event.domain == "coding"
    assert event.operation_id == "op-1"
    assert event.sequence == 1
    assert event.created_at is created_at
    assert event.delivery_hint == "coalesce"
    assert event.payload == {"text": "hello"}
    assert event.source_event_ref is None
