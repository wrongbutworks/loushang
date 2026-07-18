from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

HostStatus: TypeAlias = Literal[
    "idle",
    "running",
    "aborting",
    "disposing",
    "disposed",
]
HostLifecycleEventKind: TypeAlias = Literal[
    "run_started",
    "abort_requested",
    "run_completed",
    "run_failed",
    "run_aborted",
    "host_disposing",
    "host_disposed",
]
QueueKind: TypeAlias = Literal["steering", "follow_up"]
QueueMode: TypeAlias = Literal["all", "one-at-a-time"]


@dataclass(frozen=True)
class RunState:
    status: Literal["idle", "running"]


@dataclass(frozen=True)
class QueuedMessageSnapshot:
    id: str
    kind: QueueKind
    text: str


@dataclass(frozen=True)
class QueueSnapshot:
    steering: tuple[QueuedMessageSnapshot, ...] = ()
    follow_up: tuple[QueuedMessageSnapshot, ...] = ()


@dataclass(frozen=True)
class HostSnapshot:
    status: HostStatus
    active_run_id: str | None = None


@dataclass(frozen=True)
class HostLifecycleEvent:
    kind: HostLifecycleEventKind
    status: HostStatus
    run_id: str | None = None
    error: str | None = None
