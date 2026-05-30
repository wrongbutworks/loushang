"""Lightweight observability primitives for Loushang.

This package intentionally depends only on the Python standard library.
"""

from .context import LogContext, current_context, log_context
from .debug_log import DebugLogSink
from .logger import ObservabilityLog, get_log
from .problem import JSONValue, ProblemRecord, ProblemSeverity
from .sinks import (
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
from .trace import TraceJSONLSink

__all__ = [
    "DebugEventRecord",
    "DebugLogSink",
    "InMemoryProblemStore",
    "JSONValue",
    "LogContext",
    "ObservabilityLog",
    "ProblemRecord",
    "ProblemSeverity",
    "TraceJSONLSink",
    "capture_observability",
    "configure_debug_logging",
    "configure_observability",
    "current_context",
    "get_log",
    "is_debug_event_enabled",
    "get_problem_store",
    "log_context",
    "reset_observability",
    "restore_observability",
]
