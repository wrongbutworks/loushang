from __future__ import annotations


def test_work_public_api_exposes_only_p0_surface() -> None:
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
        "project_agent_event_to_work_events",
    }

    assert not hasattr(work, "AgentLane")
    assert not hasattr(work, "TaskLedger")
    assert not hasattr(work, "CollaborationBus")
    assert not hasattr(work, "PromptSession")
