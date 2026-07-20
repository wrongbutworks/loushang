from importlib import import_module
from typing import TYPE_CHECKING

from loushang.work.types import (
    ArtifactRef,
    ArtifactStatus,
    DeliveryHint,
    WorkEvent,
    WorkEventFact,
    WorkOperation,
    WorkPlanRun,
    WorkRun,
    WorkRunSpec,
    WorkRunStatus,
    WorkStepDeviation,
    WorkStepRun,
    WorkStepStatus,
)

if TYPE_CHECKING:
    from loushang.work.event_log import (
        EventLogBackend,
        EventLogEntry,
        EventPosition,
        InMemoryEventLogBackend,
        JsonlEventLogBackend,
    )
    from loushang.work.plan_projection import project_work_plan_runs
    from loushang.work.ports import (
        WorkAcceptPort,
        WorkCancelPort,
        WorkDomainExecutor,
        WorkExecutionContext,
        WorkQueryPort,
        WorkSubscribePort,
        WorkWaitPort,
    )
    from loushang.work.projection import (
        WorkEventProjectionContext,
        project_agent_event_to_work_events,
    )
    from loushang.work.runtime import (
        DuplicateWorkOperationError,
        UnknownWorkRunError,
        WorkLifecycleOwnershipError,
        WorkRunTerminalError,
        WorkRuntime,
        WorkRuntimeError,
    )

_LAZY_EXPORTS = {
    "EventLogBackend": ("loushang.work.event_log", "EventLogBackend"),
    "EventLogEntry": ("loushang.work.event_log", "EventLogEntry"),
    "EventPosition": ("loushang.work.event_log", "EventPosition"),
    "InMemoryEventLogBackend": (
        "loushang.work.event_log",
        "InMemoryEventLogBackend",
    ),
    "JsonlEventLogBackend": (
        "loushang.work.event_log",
        "JsonlEventLogBackend",
    ),
    "WorkEventProjectionContext": (
        "loushang.work.projection",
        "WorkEventProjectionContext",
    ),
    "project_agent_event_to_work_events": (
        "loushang.work.projection",
        "project_agent_event_to_work_events",
    ),
    "project_work_plan_runs": (
        "loushang.work.plan_projection",
        "project_work_plan_runs",
    ),
    "WorkAcceptPort": ("loushang.work.ports", "WorkAcceptPort"),
    "WorkCancelPort": ("loushang.work.ports", "WorkCancelPort"),
    "WorkDomainExecutor": ("loushang.work.ports", "WorkDomainExecutor"),
    "WorkExecutionContext": ("loushang.work.ports", "WorkExecutionContext"),
    "WorkQueryPort": ("loushang.work.ports", "WorkQueryPort"),
    "WorkSubscribePort": ("loushang.work.ports", "WorkSubscribePort"),
    "WorkWaitPort": ("loushang.work.ports", "WorkWaitPort"),
    "DuplicateWorkOperationError": (
        "loushang.work.runtime",
        "DuplicateWorkOperationError",
    ),
    "UnknownWorkRunError": ("loushang.work.runtime", "UnknownWorkRunError"),
    "WorkLifecycleOwnershipError": (
        "loushang.work.runtime",
        "WorkLifecycleOwnershipError",
    ),
    "WorkRunTerminalError": ("loushang.work.runtime", "WorkRunTerminalError"),
    "WorkRuntime": ("loushang.work.runtime", "WorkRuntime"),
    "WorkRuntimeError": ("loushang.work.runtime", "WorkRuntimeError"),
}


def __getattr__(name: str) -> object:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "ArtifactRef",
    "ArtifactStatus",
    "DeliveryHint",
    "DuplicateWorkOperationError",
    "EventLogBackend",
    "EventLogEntry",
    "EventPosition",
    "InMemoryEventLogBackend",
    "JsonlEventLogBackend",
    "WorkEventProjectionContext",
    "WorkEvent",
    "WorkEventFact",
    "WorkAcceptPort",
    "WorkCancelPort",
    "WorkDomainExecutor",
    "WorkExecutionContext",
    "WorkLifecycleOwnershipError",
    "WorkOperation",
    "WorkPlanRun",
    "WorkRun",
    "WorkRunStatus",
    "WorkRunSpec",
    "WorkRunTerminalError",
    "WorkRuntime",
    "WorkRuntimeError",
    "UnknownWorkRunError",
    "WorkQueryPort",
    "WorkSubscribePort",
    "WorkWaitPort",
    "WorkStepDeviation",
    "WorkStepRun",
    "WorkStepStatus",
    "project_agent_event_to_work_events",
    "project_work_plan_runs",
]
