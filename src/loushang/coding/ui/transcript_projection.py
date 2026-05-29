from __future__ import annotations

import re

from loushang.coding.ui.tool_blocks import ToolTranscriptBlock
from loushang.tui.transcript import ToolExecutionRecord, ToolOutputKind, ToolState

_EXIT_CODE_RE = re.compile(r"\bexit code\s+(\d+)\b", re.IGNORECASE)


def tool_block_to_record(block: ToolTranscriptBlock, *, elapsed_seconds: float = 0.0) -> ToolExecutionRecord:
    output = block.body or ""
    detail = block.detail or ""
    return ToolExecutionRecord(
        name=block.title or block.tool_name,
        state=_tool_state(block.status),
        elapsed_seconds=elapsed_seconds,
        output=output,
        output_kind=_output_kind(output),
        command=block.title if block.verb in {"Ran", "Tested"} else "",
        stderr=detail if block.status in {"error", "timed_out", "cancelled"} else "",
        exit_code=_exit_code(detail),
        show_stats=_output_kind(output) == "diff",
    )


def _tool_state(status: str) -> ToolState:
    if status == "ok":
        return "completed"
    if status in {"cancelled"}:
        return "cancelled"
    if status in {"error", "timed_out"}:
        return "failed"
    if status == "terminate":
        return "completed"
    return "running"


def _output_kind(output: str) -> ToolOutputKind:
    stripped = output.lstrip()
    if stripped.startswith("diff --git") or stripped.startswith(("@@", "--- ", "+++ ")):
        return "diff"
    return "text"


def _exit_code(detail: str) -> int | None:
    match = _EXIT_CODE_RE.search(detail)
    if match is None:
        return None
    return int(match.group(1))


__all__ = ["tool_block_to_record"]
