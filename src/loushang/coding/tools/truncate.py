from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_BYTES = 50 * 1024
GREP_MAX_LINE_LENGTH = 500
TruncationKind = Literal["lines", "bytes"]


@dataclass(frozen=True)
class TruncationResult:
    content: str
    truncated: bool
    truncated_by: TruncationKind | None
    total_lines: int = 0
    total_bytes: int = 0
    output_lines: int = 0
    output_bytes: int = 0
    last_line_partial: bool = False
    first_line_exceeds_limit: bool = False
    max_lines: int = DEFAULT_MAX_LINES
    max_bytes: int = DEFAULT_MAX_BYTES


@dataclass(frozen=True)
class LineTruncationResult:
    text: str
    was_truncated: bool


def truncate_head(
    content: str,
    *,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TruncationResult:
    _validate_limits(max_lines=max_lines, max_bytes=max_bytes)

    lines = content.splitlines(keepends=True)
    total_lines = _count_lines(content)
    total_bytes = _count_bytes(content)
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return _make_result(
            content=content,
            output_content=content,
            truncated=False,
            truncated_by=None,
            max_lines=max_lines,
            max_bytes=max_bytes,
        )

    if lines and _count_bytes(_strip_line_ending(lines[0])) > max_bytes:
        return _make_result(
            content=content,
            output_content="",
            truncated=True,
            truncated_by="bytes",
            first_line_exceeds_limit=True,
            max_lines=max_lines,
            max_bytes=max_bytes,
        )

    output_lines: list[str] = []
    output_bytes = 0
    truncated_by: TruncationKind | None = None
    for line in lines:
        if len(output_lines) >= max_lines:
            truncated_by = "lines"
            break
        line_bytes = _count_bytes(line)
        if output_bytes + line_bytes > max_bytes:
            truncated_by = "bytes"
            break
        output_lines.append(line)
        output_bytes += line_bytes

    output_content = "".join(output_lines)
    if truncated_by is None and output_content != content:
        truncated_by = "bytes" if _count_bytes(output_content) < total_bytes else "lines"

    return _make_result(
        content=content,
        output_content=output_content,
        truncated=truncated_by is not None,
        truncated_by=truncated_by,
        max_lines=max_lines,
        max_bytes=max_bytes,
    )


def truncate_tail(
    content: str,
    *,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TruncationResult:
    _validate_limits(max_lines=max_lines, max_bytes=max_bytes)

    lines = content.splitlines(keepends=True)
    total_lines = _count_lines(content)
    total_bytes = _count_bytes(content)
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return _make_result(
            content=content,
            output_content=content,
            truncated=False,
            truncated_by=None,
            max_lines=max_lines,
            max_bytes=max_bytes,
        )

    output_lines: list[str] = []
    output_bytes = 0
    truncated_by: TruncationKind | None = None
    last_line_partial = False
    for line in reversed(lines):
        if len(output_lines) >= max_lines:
            truncated_by = "lines"
            break
        line_bytes = _count_bytes(line)
        if output_bytes + line_bytes > max_bytes:
            truncated_by = "bytes"
            if not output_lines:
                clipped, clipped_by_bytes = _truncate_utf8_suffix(line, max_bytes=max_bytes)
                output_lines.append(clipped)
                output_bytes = _count_bytes(clipped)
                last_line_partial = clipped_by_bytes
            break
        output_lines.append(line)
        output_bytes += line_bytes

    output_content = "".join(reversed(output_lines))
    if truncated_by is None and output_content != content:
        truncated_by = "bytes" if _count_bytes(output_content) < total_bytes else "lines"

    return _make_result(
        content=content,
        output_content=output_content,
        truncated=truncated_by is not None,
        truncated_by=truncated_by,
        last_line_partial=last_line_partial,
        max_lines=max_lines,
        max_bytes=max_bytes,
    )


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


def _validate_limits(*, max_lines: int, max_bytes: int) -> None:
    if not isinstance(max_lines, int):
        raise TypeError("max_lines must be an integer")
    if max_lines < 1:
        raise ValueError("max_lines must be >= 1")
    if not isinstance(max_bytes, int):
        raise TypeError("max_bytes must be an integer")
    if max_bytes < 1:
        raise ValueError("max_bytes must be >= 1")


def _truncate_utf8_suffix(content: str, *, max_bytes: int) -> tuple[str, bool]:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return content, False

    start = len(encoded) - max_bytes
    clipped = encoded[start:]
    while clipped:
        try:
            return clipped.decode("utf-8"), True
        except UnicodeDecodeError:
            clipped = clipped[1:]
    return "", True


def _make_result(
    *,
    content: str,
    output_content: str,
    truncated: bool,
    truncated_by: TruncationKind | None,
    last_line_partial: bool = False,
    first_line_exceeds_limit: bool = False,
    max_lines: int,
    max_bytes: int,
) -> TruncationResult:
    return TruncationResult(
        content=output_content,
        truncated=truncated,
        truncated_by=truncated_by,
        total_lines=_count_lines(content),
        total_bytes=_count_bytes(content),
        output_lines=_count_lines(output_content),
        output_bytes=_count_bytes(output_content),
        last_line_partial=last_line_partial,
        first_line_exceeds_limit=first_line_exceeds_limit,
        max_lines=max_lines,
        max_bytes=max_bytes,
    )


formatSize = format_size
truncateHead = truncate_head
truncateTail = truncate_tail
truncateLine = truncate_line


def _count_lines(content: str) -> int:
    return len(content.splitlines()) if content else 0


def _count_bytes(content: str) -> int:
    return len(content.encode("utf-8"))


def _strip_line_ending(line: str) -> str:
    return line.removesuffix("\r\n").removesuffix("\n").removesuffix("\r")
