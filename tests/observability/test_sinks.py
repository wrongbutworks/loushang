from __future__ import annotations

import json

from loushang.observability import (
    DebugEventRecord,
    configure_debug_logging,
    configure_observability,
    current_context,
    get_log,
    get_problem_store,
    InMemoryProblemStore,
    log_context,
    reset_observability,
)
from loushang.observability.debug_log import DebugLogSink
from loushang.observability.trace import TraceJSONLSink


class _FailingObservabilitySink:
    def write_log(self, **_kwargs) -> None:
        raise OSError("debug log unavailable")

    def write_problem(self, _record) -> None:
        raise OSError("problem sink unavailable")

    def write_debug_event(self, _record) -> None:
        raise OSError("debug event sink unavailable")


def setup_function() -> None:
    reset_observability()


def test_debug_event_fans_out_to_matching_debug_and_trace_sinks(tmp_path) -> None:
    debug_path = tmp_path / "debug" / "session.log"
    debug_latest = tmp_path / "debug" / "latest"
    trace_path = tmp_path / "traces" / "session.jsonl"
    trace_latest = tmp_path / "traces" / "latest"

    configure_observability(
        debug_sink=DebugLogSink(debug_path, latest_path=debug_latest),
        trace_sink=TraceJSONLSink(trace_path, latest_path=trace_latest),
        debug_scopes={"tui"},
        trace_scopes={"tui"},
    )

    with log_context(session_id="s1", run_id=3, cwd="/repo", mode="tui"):
        get_log("loushang.tests.ui").bind(component="InlineRuntime").debug_event(
            "tui",
            "prompt.dispatch.start",
            active_run=True,
        )

    debug_text = debug_path.read_text(encoding="utf-8")
    assert "DEBUG_EVENT tui prompt.dispatch.start" in debug_text
    assert "active_run=True" in debug_text
    assert debug_latest.resolve() == debug_path

    trace_lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(trace_lines) == 1
    payload = json.loads(trace_lines[0])
    assert payload["kind"] == "debug_event"
    assert payload["scope"] == "tui"
    assert payload["name"] == "prompt.dispatch.start"
    assert payload["module"] == "loushang.tests.ui"
    assert payload["component"] == "InlineRuntime"
    assert payload["session_id"] == "s1"
    assert payload["run_id"] == 3
    assert payload["data"] == {"active_run": True}
    assert trace_latest.resolve() == trace_path


def test_debug_event_scope_filter_skips_unmatched_scope(tmp_path) -> None:
    debug_path = tmp_path / "debug.log"
    trace_path = tmp_path / "trace.jsonl"
    configure_observability(
        debug_sink=DebugLogSink(debug_path),
        trace_sink=TraceJSONLSink(trace_path),
        debug_scopes={"tui"},
        trace_scopes={"tui"},
    )

    get_log("loushang.tests.provider").debug_event("provider", "chunk.start", chars=12)

    assert not debug_path.exists()
    assert not trace_path.exists()


def test_configure_debug_logging_preserves_existing_trace_sink(tmp_path) -> None:
    debug_path = tmp_path / "debug.log"
    trace_path = tmp_path / "trace.jsonl"
    configure_observability(
        trace_sink=TraceJSONLSink(trace_path),
        trace_scopes={"provider"},
    )

    configure_debug_logging(
        debug_sink=DebugLogSink(debug_path),
        debug_scopes={"tui"},
    )

    get_log("loushang.tests.provider").debug_event("provider", "chunk.done", chars=12)
    get_log("loushang.tests.ui").debug_event("tui", "prompt.done")

    assert "prompt.done" in debug_path.read_text(encoding="utf-8")
    trace_records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [record["name"] for record in trace_records] == ["chunk.done"]


def test_configure_observability_problem_sink_preserves_existing_trace_sink(tmp_path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    problem_store = InMemoryProblemStore()
    configure_observability(
        trace_sink=TraceJSONLSink(trace_path),
        trace_scopes={"provider"},
    )

    configure_observability(problem_sink=problem_store)

    get_log("loushang.tests.provider").debug_event("provider", "chunk.done", chars=12)

    assert get_problem_store() is problem_store
    trace_records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [record["name"] for record in trace_records] == ["chunk.done"]


def test_configure_observability_explicit_none_clears_selected_sink(tmp_path) -> None:
    debug_path = tmp_path / "debug.log"
    trace_path = tmp_path / "trace.jsonl"
    configure_observability(
        debug_sink=DebugLogSink(debug_path),
        trace_sink=TraceJSONLSink(trace_path),
        debug_scopes={"tui"},
        trace_scopes={"provider"},
    )

    configure_observability(debug_sink=None)

    get_log("loushang.tests.ui").debug_event("tui", "prompt.done")
    get_log("loushang.tests.provider").debug_event("provider", "chunk.done")

    assert not debug_path.exists()
    trace_records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [record["name"] for record in trace_records] == ["chunk.done"]


def test_configure_observability_clears_scopes_with_selected_sink(tmp_path) -> None:
    first_debug_path = tmp_path / "first-debug.log"
    second_debug_path = tmp_path / "second-debug.log"
    configure_observability(
        debug_sink=DebugLogSink(first_debug_path),
        debug_scopes={"tui"},
    )

    configure_observability(debug_sink=None)
    configure_observability(debug_sink=DebugLogSink(second_debug_path))

    get_log("loushang.tests.ui").debug_event("tui", "prompt.done")

    assert not first_debug_path.exists()
    assert not second_debug_path.exists()


def test_problem_writes_to_problem_store_and_configured_sinks(tmp_path) -> None:
    debug_path = tmp_path / "debug.log"
    trace_path = tmp_path / "trace.jsonl"
    configure_observability(
        debug_sink=DebugLogSink(debug_path),
        trace_sink=TraceJSONLSink(trace_path),
        trace_scopes={"problem"},
    )

    record = get_log("loushang.tests.tool").problem(
        "tool_validation_failed",
        source="tool",
        recoverable=True,
        details={"tool": "write"},
    )

    assert "PROBLEM error tool_validation_failed" in debug_path.read_text(encoding="utf-8")
    payload = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["kind"] == "problem"
    assert payload["code"] == "tool_validation_failed"
    assert payload["source"] == "tool"
    assert payload["details"] == {"tool": "write"}
    assert record.code == "tool_validation_failed"


def test_observability_sink_failures_do_not_escape() -> None:
    configure_observability(
        debug_sink=_FailingObservabilitySink(),
        trace_sink=_FailingObservabilitySink(),
        debug_scopes={"tui"},
        trace_scopes={"problem", "tui"},
    )

    record = get_log("loushang.tests.tool").problem(
        "debug_sink_unavailable",
        source="observability",
    )
    get_log("loushang.tests.ui").debug_event("tui", "prompt.start")
    get_log("loushang.tests.ui").warning("debug log write failed")

    assert get_problem_store().all() == [record]


def test_debug_sink_does_not_replace_log_when_latest_path_matches_file(tmp_path) -> None:
    debug_path = tmp_path / "latest"
    sink = DebugLogSink(debug_path, latest_path=debug_path)

    sink.write_log(
        level="info",
        module="loushang.tests",
        component=None,
        message="hello",
        context=current_context(),
        details={},
    )

    assert debug_path.is_file()
    assert not debug_path.is_symlink()
    assert "hello" in debug_path.read_text(encoding="utf-8")


def test_debug_sink_includes_timestamp_on_human_log_lines(tmp_path) -> None:
    debug_path = tmp_path / "debug.log"
    sink = DebugLogSink(debug_path)

    sink.write_log(
        level="warning",
        module="loushang.tests",
        component=None,
        message="provider retrying",
        context=current_context(),
        details={},
    )

    text = debug_path.read_text(encoding="utf-8")
    assert text.startswith("20")
    assert " WARNING loushang.tests provider retrying\n" in text


def test_debug_sink_escapes_newlines_in_details(tmp_path) -> None:
    debug_path = tmp_path / "debug.log"
    sink = DebugLogSink(debug_path)

    sink.write_log(
        level="info",
        module="loushang.tests",
        component=None,
        message="provider event",
        context=current_context(),
        details={"payload": "line one\nline two"},
    )

    lines = debug_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "payload=line one\\nline two" in lines[0]


def test_debug_sink_escapes_newlines_in_log_message(tmp_path) -> None:
    debug_path = tmp_path / "debug.log"
    sink = DebugLogSink(debug_path)

    sink.write_log(
        level="warning",
        module="loushang.tests",
        component=None,
        message="line one\nline two",
        context=current_context(),
        details={},
    )

    lines = debug_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "line one\\nline two" in lines[0]


def test_debug_sink_escapes_newlines_in_problem_message(tmp_path) -> None:
    from loushang.observability import ProblemRecord

    debug_path = tmp_path / "debug.log"
    sink = DebugLogSink(debug_path)

    sink.write_problem(
        ProblemRecord(
            code="provider_failed",
            message="line one\nline two",
            time="2026-05-14T00:00:00Z",
        )
    )

    lines = debug_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "line one\\nline two" in lines[0]


def test_trace_sink_does_not_replace_trace_when_latest_path_matches_file(tmp_path) -> None:
    trace_path = tmp_path / "latest"
    sink = TraceJSONLSink(trace_path, latest_path=trace_path)

    get_log("loushang.tests").debug_event("tui", "prompt.start")
    configure_observability(trace_sink=sink, trace_scopes={"tui"})
    get_log("loushang.tests").debug_event("tui", "prompt.end")

    assert trace_path.is_file()
    assert not trace_path.is_symlink()
    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [record["name"] for record in records] == ["prompt.end"]


def test_trace_sink_stringifies_non_finite_floats(tmp_path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    sink = TraceJSONLSink(trace_path)

    sink.write_debug_event(
        DebugEventRecord(
            scope="provider",
            name="usage",
            data={"nan_value": float("nan"), "inf_value": float("inf")},
        )
    )

    raw_text = trace_path.read_text(encoding="utf-8")
    record = json.loads(raw_text)
    assert "NaN" not in raw_text
    assert "Infinity" not in raw_text
    assert record["data"]["nan_value"] == "nan"
    assert record["data"]["inf_value"] == "inf"
