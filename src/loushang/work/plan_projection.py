from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from loushang.work.event_log import EventLogEntry
from loushang.work.types import WorkPlanRun, WorkRunStatus, WorkStepRun, WorkStepStatus


def project_work_plan_runs(entries: Iterable[EventLogEntry]) -> tuple[WorkPlanRun, ...]:
    plan_states: list[_PlanState] = []
    active_by_plan_id: dict[str, _PlanState] = {}

    for entry in entries:
        plan_id = _entry_string_payload_value(entry, "plan_id")
        if not plan_id:
            continue

        kind = _entry_kind(entry)
        plan_state = active_by_plan_id.get(plan_id)
        if plan_state is None or _starts_new_plan_attempt(kind, plan_state):
            plan_state = _PlanState(
                plan_id=plan_id,
                method_id=_entry_string_payload_value(entry, "method_id") or None,
                status="accepted",
            )
            active_by_plan_id[plan_id] = plan_state
            plan_states.append(plan_state)

        plan_state.update_from_entry(entry, kind=kind)

    return tuple(plan_state.to_plan_run() for plan_state in plan_states)


def _starts_new_plan_attempt(kind: str, plan_state: _PlanState) -> bool:
    return plan_state.status in {"completed", "failed", "cancelled"} and kind in {"SubmitCodingTurn", "WorkPlanStarted"}


@dataclass
class _PlanState:
    plan_id: str
    status: WorkRunStatus
    method_id: str | None = None
    current_step_id: str | None = None
    error: str | None = None
    operation_ids: list[str] = field(default_factory=list)
    steps: dict[str, _StepState] = field(default_factory=dict)
    step_order: list[str] = field(default_factory=list)

    def update_from_entry(self, entry: EventLogEntry, *, kind: str) -> None:
        method_id = _entry_string_payload_value(entry, "method_id")
        if method_id:
            self.method_id = method_id
        if entry.operation_id and entry.operation_id not in self.operation_ids:
            self.operation_ids.append(entry.operation_id)

        if kind == "WorkPlanStarted":
            self.status = "running"
        elif kind == "WorkPlanCompleted":
            self.status = "completed"
        elif kind == "WorkPlanFailed":
            self.status = "failed"
            self.error = _entry_string_payload_value(entry, "error") or self.error
        elif self.status == "accepted" and kind != "SubmitCodingTurn":
            self.status = "running"

        step_id = _entry_string_payload_value(entry, "step_id")
        if not step_id:
            return
        self.current_step_id = step_id
        step_state = self._step_state(step_id)
        step_state.update_from_entry(entry, kind=kind, method_id=self.method_id, plan_id=self.plan_id)

    def _step_state(self, step_id: str) -> _StepState:
        step_state = self.steps.get(step_id)
        if step_state is not None:
            return step_state
        step_state = _StepState(step_id=step_id)
        self.steps[step_id] = step_state
        self.step_order.append(step_id)
        return step_state

    def to_plan_run(self) -> WorkPlanRun:
        steps = tuple(self.steps[step_id].to_step_run() for step_id in self._ordered_step_ids())
        metadata: dict[str, object] = {"operation_ids": tuple(self.operation_ids)}
        if self.error is not None:
            metadata["error"] = self.error
        return WorkPlanRun(
            plan_id=self.plan_id,
            status=self.status,
            method_id=self.method_id,
            current_step_id=self.current_step_id,
            steps=steps,
            step_count=len(steps),
            completed_step_count=sum(1 for step in steps if step.status == "completed"),
            failed_step_count=sum(1 for step in steps if step.status == "failed"),
            metadata=metadata,
        )

    def _ordered_step_ids(self) -> tuple[str, ...]:
        order_index = {step_id: index for index, step_id in enumerate(self.step_order)}
        return tuple(
            sorted(
                self.step_order,
                key=lambda step_id: (
                    self.steps[step_id].step_index is None,
                    self.steps[step_id].step_index if self.steps[step_id].step_index is not None else order_index[step_id],
                    order_index[step_id],
                ),
            )
        )


@dataclass
class _StepState:
    step_id: str
    status: WorkStepStatus = "pending"
    run_id: str | None = None
    plan_id: str | None = None
    method_id: str | None = None
    operation_id: str | None = None
    title: str | None = None
    step_index: int | None = None
    first_sequence: int | None = None
    started_sequence: int | None = None
    completed_sequence: int | None = None
    failed_sequence: int | None = None
    error: str | None = None

    def update_from_entry(
        self,
        entry: EventLogEntry,
        *,
        kind: str,
        method_id: str | None,
        plan_id: str,
    ) -> None:
        self.run_id = self.run_id or entry.run_id
        self.operation_id = self.operation_id or entry.operation_id
        self.method_id = method_id or self.method_id
        self.plan_id = plan_id
        self.first_sequence = self.first_sequence if self.first_sequence is not None else entry.sequence

        step_title = _entry_string_payload_value(entry, "step_title")
        if step_title:
            self.title = step_title
        step_index = _entry_step_index(entry)
        if step_index is not None:
            self.step_index = step_index

        if kind == "WorkStepStarted":
            self.status = "running"
            self.started_sequence = entry.sequence
        elif kind == "WorkStepCompleted":
            self.status = "completed"
            self.completed_sequence = entry.sequence
        elif kind == "WorkStepFailed":
            self.status = "failed"
            self.failed_sequence = entry.sequence
            self.error = _entry_string_payload_value(entry, "error") or self.error

    def to_step_run(self) -> WorkStepRun:
        metadata = _without_none(
            {
                "step_index": self.step_index,
                "operation_id": self.operation_id,
                "started_sequence": self.started_sequence,
                "completed_sequence": self.completed_sequence,
                "failed_sequence": self.failed_sequence,
                "error": self.error,
            }
        )
        return WorkStepRun(
            run_id=self.run_id or "",
            plan_id=self.plan_id or "",
            step_id=self.step_id,
            sequence=self.started_sequence if self.started_sequence is not None else self.first_sequence or 0,
            status=self.status,
            method_id=self.method_id,
            title=self.title,
            metadata=metadata,
        )


def _entry_kind(entry: EventLogEntry) -> str:
    kind = entry.payload.get("kind")
    if isinstance(kind, str) and kind:
        return kind
    return str(entry.entry_type)


def _entry_string_payload_value(entry: EventLogEntry, key: str) -> str:
    value = _entry_payload_value(entry, key)
    if isinstance(value, str):
        return value
    return ""


def _entry_step_index(entry: EventLogEntry) -> int | None:
    value = _entry_payload_value(entry, "step_index")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _entry_payload_value(entry: EventLogEntry, key: str) -> object | None:
    value = entry.payload.get(key)
    if value is not None:
        return value
    nested_payload = entry.payload.get("payload")
    if isinstance(nested_payload, Mapping):
        return nested_payload.get(key)
    return None


def _without_none(values: Mapping[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


__all__ = ["project_work_plan_runs"]
