from __future__ import annotations

from pathlib import Path

import pytest

from loushang.observability import (
    get_log,
    get_problem_store,
    log_context,
    reset_observability,
)


def setup_function() -> None:
    reset_observability()


def test_problem_records_context_module_component_and_details() -> None:
    log = get_log("loushang.tests.module").bind(component="Worker")

    with log_context(session_id="session-1", run_id=8, cwd="/repo", mode="tui"):
        record = log.problem(
            "tool_validation_failed",
            source="tool",
            recoverable=True,
            details={"tool": "write", "attempt": 2},
        )

    assert record.code == "tool_validation_failed"
    assert record.severity == "error"
    assert record.source == "tool"
    assert record.recoverable is True
    assert record.module == "loushang.tests.module"
    assert record.component == "Worker"
    assert record.session_id == "session-1"
    assert record.run_id == 8
    assert record.cwd == "/repo"
    assert record.mode == "tui"
    assert record.details == {"tool": "write", "attempt": 2}
    assert get_problem_store().all() == [record]


def test_problem_from_exception_extracts_type_and_message() -> None:
    log = get_log("loushang.tests.provider")

    try:
        raise RuntimeError("request cancelled")
    except RuntimeError as exc:
        record = log.problem_from_exception(
            exc,
            code="provider_request_cancelled",
            source="provider",
            recoverable=True,
        )

    assert record.code == "provider_request_cancelled"
    assert record.message == "request cancelled"
    assert record.exception_type == "RuntimeError"
    assert record.exception_message == "request cancelled"
    assert record.recoverable is True
    assert get_problem_store().all() == [record]


def test_problem_rejects_non_json_safe_details() -> None:
    log = get_log("loushang.tests.module")

    with pytest.raises(TypeError, match="JSON-safe"):
        log.problem("bad_details", details={"path": Path("tmp/file.txt")})
