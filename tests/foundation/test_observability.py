from __future__ import annotations

import loushang.foundation.json as foundation_json
import loushang.foundation.observability as canonical
import loushang.foundation.observability._router as canonical_router
import loushang.foundation.observability.context as canonical_context
import loushang.foundation.observability.debug_log as canonical_debug_log
import loushang.foundation.observability.logger as canonical_logger
import loushang.foundation.observability.problem as canonical_problem
import loushang.foundation.observability.problem_text as canonical_problem_text
import loushang.foundation.observability.projection as canonical_projection
import loushang.foundation.observability.records as canonical_records
import loushang.foundation.observability.runtime as canonical_runtime
import loushang.foundation.observability.runtime_identity as canonical_identity
import loushang.foundation.observability.sinks as canonical_sinks
import loushang.foundation.observability.trace as canonical_trace
import loushang.observability as compatibility
import loushang.observability.context as compatibility_context
import loushang.observability.debug_log as compatibility_debug_log
import loushang.observability.logger as compatibility_logger
import loushang.observability.problem as compatibility_problem
import loushang.observability.problem_text as compatibility_problem_text
import loushang.observability.runtime as compatibility_runtime
import loushang.observability.runtime_identity as compatibility_identity
import loushang.observability.sinks as compatibility_sinks
import loushang.observability.trace as compatibility_trace


def setup_function() -> None:
    canonical_sinks.reset_observability()


def teardown_function() -> None:
    canonical_sinks.reset_observability()


def test_canonical_observability_root_is_deliberately_small() -> None:
    assert set(canonical.__all__) == {
        "LogContext",
        "ObservabilityLog",
        "ProblemRecord",
        "ProblemSeverity",
        "get_log",
        "log_context",
    }
    assert compatibility.get_log is canonical.get_log
    assert compatibility.log_context is canonical.log_context
    assert compatibility.ProblemRecord is canonical.ProblemRecord


def test_compatibility_submodules_forward_canonical_symbols() -> None:
    identity_pairs = (
        (compatibility_context.LogContext, canonical_context.LogContext),
        (compatibility_context.current_context, canonical_context.current_context),
        (compatibility_context.log_context, canonical_context.log_context),
        (compatibility_debug_log.DebugLogSink, canonical_debug_log.DebugLogSink),
        (compatibility_logger.ObservabilityLog, canonical_logger.ObservabilityLog),
        (compatibility_logger.get_log, canonical_logger.get_log),
        (compatibility_problem.ProblemRecord, canonical_problem.ProblemRecord),
        (compatibility_problem.ProblemRecord, canonical_records.ProblemRecord),
        (compatibility_problem.ProblemSeverity, canonical_problem.ProblemSeverity),
        (
            compatibility_problem.ensure_json_safe_mapping,
            canonical_projection.ensure_json_safe_mapping,
        ),
        (
            compatibility_problem.ensure_json_safe_value,
            canonical_projection.ensure_json_safe_value,
        ),
        (
            compatibility_problem_text.ProblemRecordReader,
            canonical_problem_text.ProblemRecordReader,
        ),
        (
            compatibility_problem_text.format_problem_summary,
            canonical_problem_text.format_problem_summary,
        ),
        (
            compatibility_runtime.observability_runtime_context,
            canonical_runtime.observability_runtime_context,
        ),
        (
            compatibility_identity.RuntimeIdentityProfile,
            canonical_identity.RuntimeIdentityProfile,
        ),
        (
            compatibility_sinks.DebugEventRecord,
            canonical_records.DebugEventRecord,
        ),
        (
            compatibility_sinks.InMemoryProblemStore,
            canonical_router.InMemoryProblemStore,
        ),
        (
            compatibility_sinks.configure_observability,
            canonical_router.configure_observability,
        ),
        (
            compatibility_sinks.capture_observability,
            canonical_router.capture_observability,
        ),
        (compatibility_trace.TraceJSONLSink, canonical_trace.TraceJSONLSink),
    )

    assert all(old is new for old, new in identity_pairs)
    assert compatibility.JSONValue is foundation_json.JSONValue
    assert compatibility_problem.JSONPrimitive is foundation_json.JSONPrimitive
    assert compatibility_problem.JSONValue is foundation_json.JSONValue


def test_old_configuration_and_context_are_visible_through_new_entrypoints() -> None:
    store = canonical_sinks.InMemoryProblemStore()
    compatibility_sinks.configure_observability(problem_sink=store)

    with compatibility_context.log_context(session_id="old-session"):
        assert canonical_context.current_context().session_id == "old-session"
        record = canonical.get_log(__name__).problem("old_to_new")

    assert canonical_sinks.get_problem_store() is store
    assert store.all() == [record]


def test_new_configuration_and_context_are_visible_through_old_entrypoints() -> None:
    store = canonical_sinks.InMemoryProblemStore()
    canonical_sinks.configure_observability(problem_sink=store)

    with canonical_context.log_context(session_id="new-session"):
        assert compatibility_context.current_context().session_id == "new-session"
        record = compatibility.get_log(__name__).problem("new_to_old")

    assert compatibility_sinks.get_problem_store() is store
    assert store.all() == [record]
