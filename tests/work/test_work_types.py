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
    assert not hasattr(run, "agent_lane")
    assert not hasattr(run, "task_ledger")
    assert not hasattr(run, "collaboration_bus")


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
