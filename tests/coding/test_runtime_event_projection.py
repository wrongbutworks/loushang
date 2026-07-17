from __future__ import annotations

from datetime import UTC, datetime

from loushang.coding.event import project_runtime_event_to_session_event
from loushang.harness.events import (
    BranchSummaryCompleted,
    ContextCompactionStarted,
    PackageProgressChanged,
    QueueChanged,
    RetryCompleted,
    RuntimeEvent,
    ToolPolicyAuditEvent,
    TranscriptRecordCommitted,
)
from loushang.harness.host.retry import RetryOutcome
from loushang.harness.host.types import QueuedMessageSnapshot, QueueSnapshot


def _event(kind: str, payload: object) -> RuntimeEvent[object]:
    return RuntimeEvent(
        event_id="event-1",
        kind=kind,
        stream_id="session:s1",
        sequence=1,
        occurred_at=datetime(2026, 7, 16, tzinfo=UTC),
        session_id="s1",
        payload=payload,
    )


def test_runtime_projection_preserves_agent_owned_event() -> None:
    payload = {"type": "agent_start"}

    projected = project_runtime_event_to_session_event(
        _event("agent.agent_start", payload)
    )

    assert projected is payload


def test_runtime_projection_converts_common_session_payloads() -> None:
    queue = QueueChanged(
        QueueSnapshot(
            steering=(QueuedMessageSnapshot("q1", "steering", "adjust"),),
            follow_up=(QueuedMessageSnapshot("q2", "follow_up", "continue"),),
        )
    )
    assert project_runtime_event_to_session_event(
        _event("session.queue_update", queue)
    ) == {
        "type": "queue_update",
        "steering": ["adjust"],
        "follow_up": ["continue"],
    }
    assert project_runtime_event_to_session_event(
        _event(
            "session.compaction_start",
            ContextCompactionStarted("threshold", usage={"tokens": 90}),
        )
    ) == {
        "type": "compaction_start",
        "reason": "threshold",
        "usage": {"tokens": 90},
    }
    assert project_runtime_event_to_session_event(
        _event(
            "session.auto_retry_end",
            RetryCompleted(RetryOutcome(False, 2, error="unavailable")),
        )
    ) == {
        "type": "auto_retry_end",
        "success": False,
        "attempt": 2,
        "final_error": "unavailable",
    }
    assert project_runtime_event_to_session_event(
        _event(
            "session.auto_retry_end",
            RetryCompleted(RetryOutcome(True, 2, error="stale error")),
        )
    ) == {
        "type": "auto_retry_end",
        "success": True,
        "attempt": 2,
    }
    assert project_runtime_event_to_session_event(
        _event(
            "session.branch_summary_end",
            BranchSummaryCompleted("target", "old", "new", "summary", False, False),
        )
    ) == {
        "type": "branch_summary_end",
        "target_id": "target",
        "old_leaf_id": "old",
        "new_leaf_id": "new",
        "summary_entry_id": "summary",
        "cancelled": False,
        "aborted": False,
    }
    assert project_runtime_event_to_session_event(
        _event(
            "session.package_progress",
            PackageProgressChanged(
                progress_type="complete",
                action="install",
                source="pack",
                message="done",
                target_path="/tmp/pack",
            ),
        )
    ) == {
        "type": "package_progress",
        "progress_type": "complete",
        "action": "install",
        "source": "pack",
        "message": "done",
        "target_path": "/tmp/pack",
    }


def test_runtime_projection_hides_non_product_runtime_facts() -> None:
    committed_at = datetime(2026, 7, 16, tzinfo=UTC)
    event = _event(
        "transcript.record_committed",
        TranscriptRecordCommitted("s1", "r1", 1, committed_at),
    )

    assert project_runtime_event_to_session_event(event) is None


def test_runtime_projection_converts_tool_policy_audit_event() -> None:
    event = _event(
        "session.tool_approval_resolved",
        ToolPolicyAuditEvent(
            "tool_approval_resolved",
            {"tool_name": "write", "approval_decision": "allow"},
        ),
    )

    assert project_runtime_event_to_session_event(event) == {
        "type": "tool_approval_resolved",
        "tool_name": "write",
        "approval_decision": "allow",
    }
