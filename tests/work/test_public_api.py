from __future__ import annotations


def test_work_public_api_exposes_current_work_surface_without_multi_agent_types() -> None:
    import loushang.work as work

    assert set(work.__all__) == {
        "ArtifactRef",
        "ArtifactStatus",
        "DeliveryHint",
        "DuplicateWorkOperationError",
        "EventLogBackend",
        "EventLogEntry",
        "EventPosition",
        "InMemoryEventLogBackend",
        "JsonlEventLogBackend",
        "WorkEvent",
        "WorkEventFact",
        "WorkEventProjectionContext",
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
    }

    assert not hasattr(work, "AgentLane")
    assert not hasattr(work, "TaskLedger")
    assert not hasattr(work, "CollaborationBus")
    assert not hasattr(work, "CodingWorkShell")
    assert not hasattr(work, "PromptSession")


def test_work_ports_are_split_by_runtime_capability() -> None:
    from loushang.work.ports import (
        WorkAcceptPort,
        WorkCancelPort,
        WorkDomainExecutor,
        WorkExecutionContext,
        WorkQueryPort,
        WorkSubscribePort,
        WorkWaitPort,
    )

    assert set(WorkAcceptPort.__dict__) >= {"accept"}
    assert set(WorkWaitPort.__dict__) >= {"wait"}
    assert set(WorkCancelPort.__dict__) >= {"cancel"}
    assert set(WorkSubscribePort.__dict__) >= {"subscribe"}
    assert set(WorkQueryPort.__dict__) >= {"query"}
    assert set(WorkDomainExecutor.__dict__) >= {"execute"}
    assert set(WorkExecutionContext.__dict__) >= {"run_id", "publish"}


def test_work_projection_exports_remain_available_from_the_root_package() -> None:
    import loushang.work as work
    from loushang.work.projection import (
        WorkEventProjectionContext,
        project_agent_event_to_work_events,
    )

    assert work.WorkEventProjectionContext is WorkEventProjectionContext
    assert (
        work.project_agent_event_to_work_events
        is project_agent_event_to_work_events
    )
