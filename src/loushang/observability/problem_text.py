"""Compatibility forwarding surface for Problem text projection."""

from loushang.foundation.observability.problem_text import (
    ProblemRecordReader,
    format_problem_summary,
    is_problem_log_line,
    recent_problem_store_lines,
)

__all__ = [
    "ProblemRecordReader",
    "format_problem_summary",
    "is_problem_log_line",
    "recent_problem_store_lines",
]
