from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias

WorkRunStatus: TypeAlias = Literal[
    "accepted",
    "running",
    "cancelling",
    "completed",
    "failed",
    "cancelled",
]

WorkStepStatus: TypeAlias = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    "cancelled",
]

DeliveryHint: TypeAlias = Literal["immediate", "coalesce", "final_only"]


@dataclass(frozen=True)
class WorkOperation:
    operation_id: str
    kind: str
    session_id: str | None
    domain: str
    payload: Mapping[str, object]
    source: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkRun:
    run_id: str
    operation_id: str
    session_id: str
    domain: str
    status: WorkRunStatus
    method_id: str | None = None
    plan_id: str | None = None
    current_step_id: str | None = None


@dataclass(frozen=True)
class WorkStepRun:
    run_id: str
    plan_id: str
    step_id: str
    sequence: int
    status: WorkStepStatus
    method_id: str | None = None
    title: str | None = None
    phase: str | None = None
    activity: str | None = None
    task: str | None = None
    role: str | None = None
    expected_artifacts: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkPlanRun:
    plan_id: str
    status: WorkRunStatus
    steps: tuple[WorkStepRun, ...] = ()
    method_id: str | None = None
    current_step_id: str | None = None
    step_count: int = 0
    completed_step_count: int = 0
    failed_step_count: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkEvent:
    event_id: str
    kind: str
    run_id: str
    session_id: str
    domain: str
    operation_id: str
    sequence: int
    created_at: datetime
    delivery_hint: DeliveryHint
    payload: Mapping[str, object]
    source_event_ref: str | None = None


__all__ = [
    "DeliveryHint",
    "WorkEvent",
    "WorkOperation",
    "WorkPlanRun",
    "WorkRun",
    "WorkRunStatus",
    "WorkStepRun",
    "WorkStepStatus",
]
