from loushang.work.event_log import (
    EventLogBackend,
    EventLogEntry,
    EventPosition,
    InMemoryEventLogBackend,
    JsonlEventLogBackend,
)
from loushang.work.plan_projection import project_work_plan_runs
from loushang.work.projection import (
    WorkEventProjectionContext,
    project_agent_event_to_work_events,
)
from loushang.work.types import (
    ArtifactRef,
    ArtifactStatus,
    DeliveryHint,
    WorkEvent,
    WorkOperation,
    WorkPlanRun,
    WorkRun,
    WorkRunStatus,
    WorkStepDeviation,
    WorkStepRun,
    WorkStepStatus,
)

__all__ = [
    "ArtifactRef",
    "ArtifactStatus",
    "CodingWorkShell",
    "DeliveryHint",
    "EventLogBackend",
    "EventLogEntry",
    "EventPosition",
    "InMemoryEventLogBackend",
    "JsonlEventLogBackend",
    "WorkEventProjectionContext",
    "WorkEvent",
    "WorkOperation",
    "WorkPlanRun",
    "WorkRun",
    "WorkRunStatus",
    "WorkStepDeviation",
    "WorkStepRun",
    "WorkStepStatus",
    "project_agent_event_to_work_events",
    "project_work_plan_runs",
]


def __getattr__(name: str) -> object:
    if name == "CodingWorkShell":
        from loushang.coding.work_shell import CodingWorkShell

        return CodingWorkShell
    raise AttributeError(f"module 'loushang.work' has no attribute {name!r}")
