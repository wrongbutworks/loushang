"""Compatibility aliases for pre-split routing imports."""

from ._router import (
    DebugLogSinkProtocol,
    InMemoryProblemStore,
    TraceSinkProtocol,
    capture_observability,
    configure_debug_logging,
    configure_observability,
    emit_debug_event,
    emit_log,
    emit_problem,
    get_problem_store,
    is_debug_event_enabled,
    reset_observability,
    restore_observability,
)
from .records import DebugEventRecord

__all__ = [
    "DebugEventRecord",
    "DebugLogSinkProtocol",
    "InMemoryProblemStore",
    "TraceSinkProtocol",
    "capture_observability",
    "configure_debug_logging",
    "configure_observability",
    "emit_debug_event",
    "emit_log",
    "emit_problem",
    "get_problem_store",
    "is_debug_event_enabled",
    "reset_observability",
    "restore_observability",
]
