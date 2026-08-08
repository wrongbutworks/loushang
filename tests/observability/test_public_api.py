from __future__ import annotations

import importlib

import loushang.observability as observability


def test_observability_public_surface_is_frozen_for_compatibility() -> None:
    assert set(observability.__all__) == {
        "DebugEventRecord",
        "DebugLogSink",
        "InMemoryProblemStore",
        "JSONValue",
        "LogContext",
        "ObservabilityLog",
        "ProblemRecord",
        "ProblemRecordReader",
        "ProblemSeverity",
        "RuntimeIdentityProfile",
        "TraceJSONLSink",
        "capture_observability",
        "collect_profiled_runtime_identity",
        "collect_runtime_identity",
        "configure_debug_logging",
        "configure_observability",
        "current_context",
        "disable_debug_file",
        "enable_debug_file",
        "format_problem_summary",
        "format_profiled_runtime_identity_text",
        "format_runtime_identity_text",
        "get_log",
        "get_problem_store",
        "is_debug_event_enabled",
        "is_problem_log_line",
        "log_context",
        "observability_runtime_context",
        "parse_scopes",
        "path_from_args_or_env",
        "recent_problem_store_lines",
        "reset_observability",
        "restore_observability",
        "session_log_label",
        "value_from_args_or_env",
    }
    assert all(hasattr(observability, name) for name in observability.__all__)


def test_observability_direct_submodule_paths_remain_importable() -> None:
    submodules = {
        "context",
        "debug_log",
        "logger",
        "problem",
        "problem_text",
        "runtime",
        "runtime_identity",
        "sinks",
        "trace",
    }

    assert {
        importlib.import_module(f"loushang.observability.{name}").__name__
        for name in submodules
    } == {f"loushang.observability.{name}" for name in submodules}
