from __future__ import annotations


def test_coding_diagnostics_paths_share_harness_identity() -> None:
    import loushang.coding as coding
    import loushang.coding.diagnostics as diagnostics
    from loushang.coding.diagnostics import service as service_compatibility
    from loushang.coding.diagnostics import types as types_compatibility
    from loushang.harness.diagnostics import service, types

    type_names = (
        "DiagnosticLevel",
        "DiagnosticPhase",
        "DiagnosticRecord",
        "DiagnosticSource",
        "DiagnosticSummary",
        "DiagnosticsQuery",
        "ErrorReport",
        "StartupCheck",
        "StartupCheckResult",
    )
    for name in type_names:
        assert getattr(diagnostics, name) is getattr(types, name)
        assert getattr(types_compatibility, name) is getattr(types, name)

    coding_names = (
        "DiagnosticRecord",
        "DiagnosticSummary",
        "DiagnosticsQuery",
        "ErrorReport",
        "StartupCheck",
        "StartupCheckResult",
    )
    for name in coding_names:
        assert getattr(coding, name) is getattr(types, name)

    assert diagnostics.DiagnosticsService is service.DiagnosticsService
    assert service_compatibility.DiagnosticsService is service.DiagnosticsService
    assert coding.DiagnosticsService is service.DiagnosticsService
    assert types.DiagnosticRecord.__module__ == "loushang.harness.diagnostics.types"
    assert service.DiagnosticsService.__module__ == "loushang.harness.diagnostics.service"


def test_coding_serialization_remains_product_owned() -> None:
    from loushang.coding.diagnostics import serialize_diagnostic
    from loushang.harness.diagnostics.types import DiagnosticRecord

    record = DiagnosticRecord(
        type="error",
        code="tool_failed",
        message="Tool failed.",
        phase="runtime",
        source="tool",
        timestamp="2026-07-12T00:00:00Z",
        session_id="s1",
    )

    assert serialize_diagnostic.__module__ == "loushang.coding.diagnostics.serialization"
    assert serialize_diagnostic(record) == {
        "type": "error",
        "code": "tool_failed",
        "message": "Tool failed.",
        "phase": "runtime",
        "source": "tool",
        "timestamp": "2026-07-12T00:00:00Z",
        "details": {},
        "occurrenceCount": 1,
        "sessionId": "s1",
    }


def test_coding_problem_bridge_records_harness_diagnostics() -> None:
    from loushang.coding.diagnostics.problem_bridge import DiagnosticsProblemStore
    from loushang.harness.diagnostics.service import DiagnosticsService
    from loushang.harness.diagnostics.types import DiagnosticRecord
    from loushang.observability import ProblemRecord

    service = DiagnosticsService()
    store = DiagnosticsProblemStore(service)
    store.record_problem(
        ProblemRecord(
            code="tool_failed",
            severity="error",
            source="tool",
            message="Tool failed.",
            time="2026-07-12T00:00:00Z",
            session_id="s1",
            mode="runtime",
        )
    )

    records = service.get_last_diagnostics()
    assert len(records) == 1
    assert isinstance(records[0], DiagnosticRecord)
    assert records[0].code == "tool_failed"
    assert records[0].source == "tool"
