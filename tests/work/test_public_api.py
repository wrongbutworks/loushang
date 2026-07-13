from __future__ import annotations


def test_work_public_api_exposes_current_work_surface_without_multi_agent_types() -> None:
    import loushang.work as work

    assert set(work.__all__) == {
        "ArtifactRef",
        "ArtifactStatus",
        "DeliveryHint",
        "EventLogBackend",
        "EventLogEntry",
        "EventPosition",
        "InMemoryEventLogBackend",
        "JsonlEventLogBackend",
        "WorkEvent",
        "WorkEventProjectionContext",
        "WorkOperation",
        "WorkPlanRun",
        "WorkRun",
        "WorkRunStatus",
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
