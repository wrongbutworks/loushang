from __future__ import annotations


def test_work_public_api_exposes_current_work_surface_without_multi_agent_types() -> None:
    import loushang.work as work

    assert set(work.__all__) == {
        "CodingWorkShell",
        "DeliveryHint",
        "EventLogBackend",
        "EventLogEntry",
        "EventPosition",
        "InMemoryEventLogBackend",
        "JsonlEventLogBackend",
        "WorkEvent",
        "WorkEventProjectionContext",
        "WorkOperation",
        "WorkRun",
        "WorkRunStatus",
        "WorkStepRun",
        "WorkStepStatus",
        "project_agent_event_to_work_events",
    }

    assert not hasattr(work, "AgentLane")
    assert not hasattr(work, "TaskLedger")
    assert not hasattr(work, "CollaborationBus")
    assert not hasattr(work, "PromptSession")
