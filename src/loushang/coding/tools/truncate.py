from __future__ import annotations

from dataclasses import dataclass

from loushang.harness.workspace.truncation import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    TruncationKind,
    TruncationResult,
    truncate_head,
    truncate_tail,
)

GREP_MAX_LINE_LENGTH = 500


@dataclass(frozen=True)
class LineTruncationResult:
    text: str
    was_truncated: bool


def format_size(byte_count: int) -> str:
    if byte_count < 1024:
        return f"{byte_count}B"
    if byte_count < 1024 * 1024:
        return f"{byte_count / 1024:.1f}KB"
    return f"{byte_count / (1024 * 1024):.1f}MB"


def truncate_line(line: str, max_chars: int = GREP_MAX_LINE_LENGTH) -> LineTruncationResult:
    if not isinstance(max_chars, int):
        raise TypeError("max_chars must be an integer")
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    if len(line) <= max_chars:
        return LineTruncationResult(text=line, was_truncated=False)
    return LineTruncationResult(text=f"{line[:max_chars]}... [truncated]", was_truncated=True)


def truncation_details(result: TruncationResult) -> dict[str, object]:
    return {
        "truncated": result.truncated,
        "truncated_by": result.truncated_by,
        "total_lines": result.total_lines,
        "total_bytes": result.total_bytes,
        "output_lines": result.output_lines,
        "output_bytes": result.output_bytes,
        "last_line_partial": result.last_line_partial,
        "first_line_exceeds_limit": result.first_line_exceeds_limit,
        "max_lines": result.max_lines,
        "max_bytes": result.max_bytes,
    }


formatSize = format_size
truncateHead = truncate_head
truncateTail = truncate_tail
truncateLine = truncate_line


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_LINES",
    "GREP_MAX_LINE_LENGTH",
    "LineTruncationResult",
    "TruncationKind",
    "TruncationResult",
    "format_size",
    "formatSize",
    "truncate_head",
    "truncate_line",
    "truncate_tail",
    "truncateHead",
    "truncateLine",
    "truncateTail",
    "truncation_details",
]
