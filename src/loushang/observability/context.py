"""Compatibility forwarding surface for observability context."""

from loushang.foundation.observability.context import (
    LogContext,
    current_context,
    log_context,
)

__all__ = ["LogContext", "current_context", "log_context"]
