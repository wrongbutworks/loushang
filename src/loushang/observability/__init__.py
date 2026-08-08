"""Compatibility facade for :mod:`loushang.foundation.observability`."""

from loushang.foundation.observability.context import (
    LogContext,
    current_context,
    log_context,
)
from loushang.foundation.observability.debug_log import DebugLogSink
from loushang.foundation.observability.logger import ObservabilityLog, get_log
from loushang.foundation.observability.problem import (
    JSONValue,
    ProblemRecord,
    ProblemSeverity,
)
from loushang.foundation.observability.problem_text import (
    ProblemRecordReader,
    format_problem_summary,
    is_problem_log_line,
    recent_problem_store_lines,
)
from loushang.foundation.observability.runtime import (
    disable_debug_file,
    enable_debug_file,
    observability_runtime_context,
    parse_scopes,
    path_from_args_or_env,
    session_log_label,
    value_from_args_or_env,
)
from loushang.foundation.observability.runtime_identity import (
    RuntimeIdentityProfile,
    collect_profiled_runtime_identity,
    collect_runtime_identity,
    format_profiled_runtime_identity_text,
    format_runtime_identity_text,
)
from loushang.foundation.observability.sinks import (
    DebugEventRecord,
    InMemoryProblemStore,
    capture_observability,
    configure_debug_logging,
    configure_observability,
    get_problem_store,
    is_debug_event_enabled,
    reset_observability,
    restore_observability,
)
from loushang.foundation.observability.trace import TraceJSONLSink

__all__ = [
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
    "configure_debug_logging",
    "configure_observability",
    "collect_runtime_identity",
    "collect_profiled_runtime_identity",
    "current_context",
    "disable_debug_file",
    "enable_debug_file",
    "format_problem_summary",
    "format_runtime_identity_text",
    "format_profiled_runtime_identity_text",
    "get_log",
    "is_debug_event_enabled",
    "is_problem_log_line",
    "get_problem_store",
    "log_context",
    "observability_runtime_context",
    "parse_scopes",
    "path_from_args_or_env",
    "reset_observability",
    "recent_problem_store_lines",
    "restore_observability",
    "session_log_label",
    "value_from_args_or_env",
]
