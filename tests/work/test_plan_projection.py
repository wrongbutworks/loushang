from __future__ import annotations

from datetime import UTC, datetime


def _entry(
    entry_id: str,
    *,
    kind: str,
    run_id: str,
    sequence: int,
    operation_id: str | None = None,
    entry_type: str = "event",
    method_id: str | None = "method:task:review",
    plan_id: str | None = "plan:method:task:review",
    step_id: str | None = None,
    step_index: int | None = None,
    step_title: str | None = None,
    error: str | None = None,
) -> object:
    from loushang.work import EventLogEntry

    payload: dict[str, object] = {"kind": kind}
    nested_payload: dict[str, object] = {}
    if method_id is not None:
        nested_payload["method_id"] = method_id
    if plan_id is not None:
        nested_payload["plan_id"] = plan_id
    if step_id is not None:
        nested_payload["step_id"] = step_id
    if step_index is not None:
        nested_payload["step_index"] = step_index
    if step_title is not None:
        nested_payload["step_title"] = step_title
    if error is not None:
        nested_payload["error"] = error
    if nested_payload:
        payload["payload"] = nested_payload

    return EventLogEntry(
        entry_id=entry_id,
        entry_type=entry_type,
        operation_id=operation_id or f"op-{run_id}",
        event_id=None if entry_type == "operation" else f"event-{entry_id}",
        run_id=run_id,
        session_id="session-1",
        sequence=sequence,
        payload=payload,
        created_at=datetime(2026, 6, 1, 10, 30, sequence, tzinfo=UTC),
    )


def _step_entries(
    *,
    run_id: str,
    step_id: str,
    step_index: int,
    step_title: str,
    first: bool = False,
    last: bool = False,
    failed: bool = False,
) -> list[object]:
    entries = [
        _entry(
            f"{run_id}-operation",
            kind="SubmitCodingTurn",
            run_id=run_id,
            sequence=0,
            entry_type="operation",
            step_id=step_id,
            step_index=step_index,
            step_title=step_title,
        ),
        _entry(f"{run_id}-run-started", kind="WorkRunStarted", run_id=run_id, sequence=1, step_id=step_id),
    ]
    if first:
        entries.append(
            _entry(
                f"{run_id}-plan-started",
                kind="WorkPlanStarted",
                run_id=run_id,
                sequence=2,
                step_id=step_id,
                step_index=step_index,
                step_title=step_title,
            )
        )
    entries.append(
        _entry(
            f"{run_id}-step-started",
            kind="WorkStepStarted",
            run_id=run_id,
            sequence=3,
            step_id=step_id,
            step_index=step_index,
            step_title=step_title,
        )
    )
    if failed:
        entries.extend(
            [
                _entry(
                    f"{run_id}-step-failed",
                    kind="WorkStepFailed",
                    run_id=run_id,
                    sequence=4,
                    step_id=step_id,
                    step_index=step_index,
                    step_title=step_title,
                    error="step failed",
                ),
                _entry(
                    f"{run_id}-plan-failed",
                    kind="WorkPlanFailed",
                    run_id=run_id,
                    sequence=5,
                    step_id=step_id,
                    step_index=step_index,
                    step_title=step_title,
                    error="step failed",
                ),
            ]
        )
    else:
        entries.append(
            _entry(
                f"{run_id}-step-completed",
                kind="WorkStepCompleted",
                run_id=run_id,
                sequence=4,
                step_id=step_id,
                step_index=step_index,
                step_title=step_title,
            )
        )
        if last:
            entries.append(
                _entry(
                    f"{run_id}-plan-completed",
                    kind="WorkPlanCompleted",
                    run_id=run_id,
                    sequence=5,
                    step_id=step_id,
                    step_index=step_index,
                    step_title=step_title,
                )
            )
    entries.append(_entry(f"{run_id}-run-completed", kind="WorkRunCompleted", run_id=run_id, sequence=6, step_id=step_id))
    return entries


def test_project_work_plan_runs_replays_completed_steps_across_turn_runs() -> None:
    from loushang.work import project_work_plan_runs

    plans = project_work_plan_runs(
        [
            *_step_entries(
                run_id="run-inspect",
                step_id="inspect",
                step_index=0,
                step_title="Inspect current changes",
                first=True,
            ),
            *_step_entries(
                run_id="run-verify",
                step_id="verify",
                step_index=1,
                step_title="Run focused checks",
                last=True,
            ),
        ]
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.plan_id == "plan:method:task:review"
    assert plan.method_id == "method:task:review"
    assert plan.status == "completed"
    assert plan.step_count == 2
    assert plan.completed_step_count == 2
    assert plan.failed_step_count == 0
    assert plan.current_step_id == "verify"
    assert plan.metadata["operation_ids"] == ("op-run-inspect", "op-run-verify")

    assert [(step.step_id, step.status, step.run_id, step.title) for step in plan.steps] == [
        ("inspect", "completed", "run-inspect", "Inspect current changes"),
        ("verify", "completed", "run-verify", "Run focused checks"),
    ]
    assert plan.steps[0].metadata == {
        "step_index": 0,
        "operation_id": "op-run-inspect",
        "started_sequence": 3,
        "completed_sequence": 4,
    }


def test_project_work_plan_runs_replays_failed_step_and_plan_error() -> None:
    from loushang.work import project_work_plan_runs

    plans = project_work_plan_runs(
        _step_entries(
            run_id="run-verify",
            step_id="verify",
            step_index=1,
            step_title="Run focused checks",
            first=True,
            failed=True,
        )
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.status == "failed"
    assert plan.completed_step_count == 0
    assert plan.failed_step_count == 1
    assert plan.current_step_id == "verify"
    assert plan.metadata["error"] == "step failed"
    assert plan.steps[0].status == "failed"
    assert plan.steps[0].metadata["error"] == "step failed"
    assert plan.steps[0].metadata["failed_sequence"] == 4


def test_project_work_plan_runs_ignores_entries_without_plan_id() -> None:
    from loushang.work import project_work_plan_runs

    plans = project_work_plan_runs(
        [
            _entry(
                "run-1-operation",
                kind="SubmitCodingTurn",
                run_id="run-1",
                sequence=0,
                entry_type="operation",
                method_id=None,
                plan_id=None,
            ),
            _entry("run-1-started", kind="WorkRunStarted", run_id="run-1", sequence=1, method_id=None, plan_id=None),
        ]
    )

    assert plans == ()
