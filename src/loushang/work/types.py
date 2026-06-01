from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Mapping, TypeAlias


WorkRunStatus: TypeAlias = Literal[
    "accepted",
    "running",
    "cancelling",
    "completed",
    "failed",
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
    "WorkRun",
    "WorkRunStatus",
]
