from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from loushang.ai.types import AssistantMessage, TextPart, Usage
from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
from loushang.coding.loader import ResourceDiagnostic
from loushang.coding.session.session_diagnostics_bridge import SessionDiagnosticsBridge
from loushang.coding.store import SessionManager


def test_session_diagnostics_bridge_filters_session_views(tmp_path) -> None:
    diagnostics = DiagnosticsService()
    manager = SessionManager.new(
        session_dir=tmp_path, cwd="/tmp/project", persist=False
    )
    bridge = SessionDiagnosticsBridge(
        diagnostics_service=diagnostics,
        session_manager=manager,
        get_extension_runner=lambda: None,
    )
    diagnostics.record(
        diagnostics.normalize_exception(
            code="current_session_error",
            exc="boom",
            phase="runtime",
            source="session",
            session_id=manager.get_header().conversation_id,
        )
    )
    diagnostics.record(
        diagnostics.normalize_exception(
            code="other_session_error",
            exc="other",
            phase="runtime",
            source="session",
            session_id="other-session",
        )
    )

    assert [record.code for record in bridge.get_session_diagnostics()] == [
        "current_session_error"
    ]
    assert [
        record.code
        for record in bridge.get_session_diagnostics(
            DiagnosticsQuery(code="current_session_error")
        )
    ] == ["current_session_error"]
    assert bridge.get_session_diagnostics_summary().total_count == 1


def test_session_diagnostics_bridge_syncs_new_extension_diagnostics_once(
    tmp_path,
) -> None:
    diagnostics = DiagnosticsService()
    manager = SessionManager.new(
        session_dir=tmp_path, cwd="/tmp/project", persist=False
    )
    extension_diagnostics = [
        ResourceDiagnostic(code="already_seen", message="old"),
        ResourceDiagnostic(
            code="extension_session_refresh_failed",
            message="refresh failed",
            source_path=Path("/tmp/project/extensions/demo.py"),
        ),
    ]
    runner = SimpleNamespace(get_diagnostics=lambda: extension_diagnostics)
    bridge = SessionDiagnosticsBridge(
        diagnostics_service=diagnostics,
        session_manager=manager,
        get_extension_runner=lambda: runner,
        recorded_extension_diagnostics=1,
    )

    bridge.sync_extension_diagnostics(phase="runtime")
    bridge.sync_extension_diagnostics(phase="runtime")

    records = diagnostics.get_diagnostics()
    assert [record.code for record in records] == ["extension_session_refresh_failed"]
    assert records[0].type == "error"
    assert records[0].source == "extensions"
    assert records[0].session_id == manager.get_header().conversation_id
    assert records[0].entry_id == manager.get_leaf_id()


def test_session_diagnostics_bridge_records_runtime_errors_with_session_context(
    tmp_path,
) -> None:
    diagnostics = DiagnosticsService()
    manager = SessionManager.new(
        session_dir=tmp_path, cwd="/tmp/project", persist=False
    )
    bridge = SessionDiagnosticsBridge(
        diagnostics_service=diagnostics,
        session_manager=manager,
        get_extension_runner=lambda: None,
    )
    assistant_message = AssistantMessage(
        role="assistant",
        content=[],
        api="responses",
        provider="demo",
        model="demo-model",
        response_id="resp_1",
        usage=Usage(
            input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
        ),
        stop_reason="error",
        error_message="provider failed",
        timestamp=0.0,
    )
    tool_result = SimpleNamespace(
        content=[TextPart(type="text", text="tool failed")], details={"exit_code": 1}
    )

    bridge.record_runtime_exception(code="runtime_failed", exc="runtime boom")
    bridge.record_assistant_response_error(assistant_message)
    bridge.record_tool_execution_error(
        {
            "tool_call_id": "tc1",
            "tool_name": "shell",
            "result": tool_result,
        }
    )

    records = diagnostics.get_diagnostics()
    assert [record.code for record in records] == [
        "runtime_failed",
        "assistant_response_error",
        "tool_execution_failed",
    ]
    assert {record.session_id for record in records} == {manager.get_header().conversation_id}
    assert records[1].details["response_id"] == "resp_1"
    assert records[2].message == "tool failed"
    assert records[2].details["tool_call_id"] == "tc1"


def test_session_diagnostics_bridge_records_policy_tool_errors_with_correlation(
    tmp_path,
) -> None:
    diagnostics = DiagnosticsService()
    manager = SessionManager.new(
        session_dir=tmp_path, cwd="/tmp/project", persist=False
    )
    bridge = SessionDiagnosticsBridge(
        diagnostics_service=diagnostics,
        session_manager=manager,
        get_extension_runner=lambda: None,
    )
    tool_result = SimpleNamespace(
        content=[TextPart(type="text", text="Tool write is blocked by policy")],
        details={
            "tool_name": "write",
            "policy_disposition": "deny",
            "policy_code": "tool_blocked",
            "policy_reason": "Tool write is blocked by policy",
            "approval_required": False,
            "argument_keys": ["content", "path"],
            "path": "/tmp/project/blocked.txt",
        },
    )

    bridge.record_tool_execution_error(
        {
            "tool_call_id": "tc-policy-1",
            "tool_name": "write",
            "result": tool_result,
        }
    )

    records = diagnostics.get_diagnostics()
    assert [record.code for record in records] == [
        "tool_execution_failed",
        "tool_blocked",
    ]
    policy_records = diagnostics.get_diagnostics(
        query=DiagnosticsQuery(tool_call_id="tc-policy-1", code="tool_blocked")
    )
    assert len(policy_records) == 1
    assert policy_records[0].type == "warning"
    assert policy_records[0].source == "policy"
    assert policy_records[0].phase == "runtime"
    assert policy_records[0].message == "Tool write is blocked by policy"
    assert policy_records[0].session_id == manager.get_header().conversation_id
    assert policy_records[0].details["tool_call_id"] == "tc-policy-1"
    assert policy_records[0].details["tool_name"] == "write"
    assert policy_records[0].details["policy_disposition"] == "deny"
    assert (
        policy_records[0].details["policy_reason"] == "Tool write is blocked by policy"
    )
    assert policy_records[0].details["path"] == "/tmp/project/blocked.txt"


def test_session_diagnostics_bridge_projects_tool_details_before_recording(
    tmp_path,
) -> None:
    from loushang.agent import AgentToolResult, FunctionalToolOutputProjector

    diagnostics = DiagnosticsService()
    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )
    bridge = SessionDiagnosticsBridge(
        diagnostics_service=diagnostics,
        session_manager=manager,
        get_extension_runner=lambda: None,
    )
    raw_details = object()
    result = AgentToolResult(
        content=[TextPart(type="text", text="tool failed")],
        details=raw_details,
        projector=FunctionalToolOutputProjector(
            transcript=lambda details: {"surface": "transcript"},
            event=lambda details: {
                "surface": "event",
                "policy_disposition": "deny",
                "policy_code": "tool_blocked",
            },
        ),
    )

    bridge.record_tool_execution_error(
        {
            "tool_call_id": "tc-rich",
            "tool_name": "write",
            "result": result,
        }
    )

    records = diagnostics.get_diagnostics()
    assert records[0].details["result_details"] == {
        "surface": "event",
        "policy_disposition": "deny",
        "policy_code": "tool_blocked",
    }
    assert records[1].details["surface"] == "event"
    assert repr(raw_details) not in repr(records[0].details)


def test_session_diagnostics_bridge_drops_unsafe_legacy_tool_details(tmp_path) -> None:
    diagnostics = DiagnosticsService()
    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )
    bridge = SessionDiagnosticsBridge(
        diagnostics_service=diagnostics,
        session_manager=manager,
        get_extension_runner=lambda: None,
    )

    bridge.record_tool_execution_error(
        {
            "tool_call_id": "tc-legacy",
            "tool_name": "legacy",
            "result": SimpleNamespace(
                content=[TextPart(type="text", text="tool failed")],
                details={"path": Path("notes.txt")},
            ),
        }
    )

    record = diagnostics.get_diagnostics()[0]
    assert record.details["result_details"] == {}
    assert "notes.txt" not in repr(record.details)
