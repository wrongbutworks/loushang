from __future__ import annotations

from loushang.coding.diagnostics.types import DiagnosticPhase, DiagnosticRecord, DiagnosticSource
from loushang.observability import InMemoryProblemStore, ProblemRecord


class DiagnosticsProblemStore(InMemoryProblemStore):
    def __init__(self, diagnostics_service) -> None:
        super().__init__()
        self._diagnostics_service = diagnostics_service

    def record_problem(self, record: ProblemRecord) -> None:
        super().record_problem(record)
        self._diagnostics_service.record(_problem_to_diagnostic(record))


def _problem_to_diagnostic(record: ProblemRecord) -> DiagnosticRecord:
    return DiagnosticRecord(
        type=record.severity,
        code=record.code,
        message=record.message,
        phase=_diagnostic_phase(record),
        source=_diagnostic_source(record),
        timestamp=record.time,
        session_id=record.session_id,
        details=_diagnostic_details(record),
    )


def _diagnostic_phase(record: ProblemRecord) -> DiagnosticPhase:
    if record.mode == "startup":
        return "startup"
    if record.mode == "resource_loading":
        return "resource_loading"
    return "runtime"


def _diagnostic_source(record: ProblemRecord) -> DiagnosticSource:
    source = record.source or "diagnostics"
    if source in _DIAGNOSTIC_SOURCES:
        return source  # type: ignore[return-value]
    if source == "config":
        return "model"
    return "diagnostics"


def _diagnostic_details(record: ProblemRecord) -> dict[str, object]:
    details: dict[str, object] = dict(record.details)
    details["problem_source"] = record.source
    details["recoverable"] = record.recoverable
    if record.mode is not None:
        details["mode"] = record.mode
    if record.run_id is not None:
        details["run_id"] = record.run_id
    if record.exception_type is not None:
        details["exception_type"] = record.exception_type
    if record.exception_message is not None:
        details["exception_message"] = record.exception_message
    return details


_DIAGNOSTIC_SOURCES = frozenset(
    {
        "bootstrap",
        "loader",
        "extensions",
        "session",
        "policy",
        "exec",
        "tool",
        "diagnostics",
        "provider",
        "model",
        "agent",
    }
)


__all__ = ["DiagnosticsProblemStore"]
