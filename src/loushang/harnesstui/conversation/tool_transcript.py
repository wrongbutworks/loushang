from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from loushang.harness.tools.workspace.output_preview import (
    collapse_tool_output_preview,
    drop_tool_timing_tail_line,
    prefers_tail_tool_output,
)
from loushang.tui.render import diff_stat
from loushang.tui.transcript import ToolExecutionRecord, ToolOutputKind, ToolState

ToolTranscriptStatus = Literal[
    "running", "ok", "error", "cancelled", "timed_out", "terminate"
]
ToolVerbResolver = Callable[[str, object | None], str]
ToolBodyVisibility = Callable[[str, ToolTranscriptStatus], bool]
ToolCommandResolver = Callable[[str, object | None, str], str | None]

_EXIT_CODE_RE = re.compile(r"\bexit code\s+(\d+)\b", re.IGNORECASE)


def _default_verb(tool_name: str, args: object | None) -> str:
    del args
    return f"Used {tool_name}"


def _hide_body(tool_name: str, status: ToolTranscriptStatus) -> bool:
    del tool_name, status
    return False


def _hide_command(tool_name: str, args: object | None, title: str) -> str | None:
    del tool_name, args, title
    return None


@dataclass(frozen=True)
class ToolCallView:
    """Product-neutral input for one tool call shown in a conversation."""

    tool_call_id: str
    tool_name: str
    args: object | None = None
    rendered_text: str | None = None


@dataclass(frozen=True)
class ToolResultView:
    """Product-neutral input for one tool result shown in a conversation."""

    tool_call_id: str
    tool_name: str
    status: ToolTranscriptStatus
    args: object | None = None
    result_text: str = ""
    rendered_text: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    error_summary: str | None = None


@dataclass(frozen=True)
class ToolCallSnapshot:
    tool_name: str
    args: object | None = None
    rendered_call_text: str | None = None


@dataclass(frozen=True)
class ToolTranscriptBlock:
    tool_call_id: str
    tool_name: str
    status: ToolTranscriptStatus
    verb: str
    title: str
    detail: str | None = None
    body: str | None = None
    command: str | None = None


@dataclass
class ToolTranscriptProjector:
    """Project neutral tool call/result views into reusable transcript blocks."""

    verb_resolver: ToolVerbResolver = _default_verb
    body_visibility: ToolBodyVisibility = _hide_body
    command_resolver: ToolCommandResolver = _hide_command
    max_body_lines: int = 8

    def remember_call(self, view: ToolCallView) -> ToolCallSnapshot:
        return ToolCallSnapshot(
            tool_name=view.tool_name,
            args=view.args,
            rendered_call_text=view.rendered_text,
        )

    def project_result(
        self,
        view: ToolResultView,
        snapshot: ToolCallSnapshot | None = None,
    ) -> ToolTranscriptBlock:
        tool_name = snapshot.tool_name if snapshot is not None else view.tool_name
        args = snapshot.args if snapshot is not None else view.args
        rendered_call = snapshot.rendered_call_text if snapshot is not None else None
        title = _title(tool_name, args, rendered_call)
        return ToolTranscriptBlock(
            tool_call_id=view.tool_call_id,
            tool_name=tool_name,
            status=view.status,
            verb=self.verb_resolver(tool_name, args),
            title=title,
            detail=_detail(view, tool_name=tool_name),
            body=_body(
                tool_name,
                view,
                visible=self.body_visibility(tool_name, view.status),
                max_lines=self.max_body_lines,
            ),
            command=self.command_resolver(tool_name, args, title),
        )


def tool_block_to_record(
    block: ToolTranscriptBlock, *, elapsed_seconds: float = 0.0
) -> ToolExecutionRecord:
    output = block.body or ""
    detail = block.detail or ""
    output_kind = _output_kind(output)
    return ToolExecutionRecord(
        name=block.title or block.tool_name,
        state=_tool_state(block.status),
        elapsed_seconds=elapsed_seconds,
        output=output,
        output_kind=output_kind,
        command=block.command or "",
        stderr=(detail if block.status in {"error", "timed_out", "cancelled"} else ""),
        exit_code=_exit_code(detail),
        show_stats=output_kind == "diff",
    )


def _title(tool_name: str, args: object | None, rendered_call: str | None) -> str:
    if rendered_call:
        first_line = rendered_call.splitlines()[0].strip()
        if first_line.startswith("$ "):
            return f"{tool_name} {first_line[2:].strip()}"
        if first_line:
            return first_line
    detail = _arg_detail(args)
    return f"{tool_name} {detail}" if detail else tool_name


def _arg_detail(args: object | None) -> str | None:
    if isinstance(args, Mapping):
        for key in ("path", "file_path", "pattern", "query", "command"):
            value = args.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _detail(view: ToolResultView, *, tool_name: str) -> str | None:
    if view.status == "ok":
        return _ok_detail(view.details, tool_name=tool_name)
    if view.status == "error":
        return f"failed: {view.error_summary}" if view.error_summary else "failed"
    if view.status == "timed_out":
        return "timed out"
    if view.status == "cancelled":
        return "cancelled"
    if view.status == "terminate":
        return "terminated"
    return None


def _ok_detail(details: Mapping[str, Any], *, tool_name: str) -> str | None:
    if not details:
        return None
    normalized = tool_name.lower()
    if any(part in normalized for part in ("edit", "patch")):
        return diff_stat(details.get("diff"))
    if "write" in normalized:
        return _write_stat(details)
    return None


def _write_stat(details: Mapping[str, Any]) -> str | None:
    parts: list[str] = []
    operation = details.get("operation")
    if isinstance(operation, str) and operation:
        parts.append(_write_operation_label(operation))
    bytes_written = details.get("bytes_written", details.get("bytesWritten"))
    formatted_size = _format_byte_count(bytes_written)
    if formatted_size:
        parts.append(formatted_size)
    return ", ".join(parts) if parts else None


def _write_operation_label(operation: str) -> str:
    normalized = operation.lower()
    if normalized == "create":
        return "created"
    if normalized == "overwrite":
        return "overwrote"
    return normalized.replace("_", " ")


def _format_byte_count(value: object) -> str | None:
    if not isinstance(value, int) or value < 0:
        return None
    if value < 1024:
        return f"{value} B"
    units = ("KiB", "MiB", "GiB")
    amount = float(value)
    for unit in units:
        amount /= 1024
        if amount < 1024:
            return f"{amount:.1f} {unit}"
    return f"{amount:.1f} TiB"


def _body(
    tool_name: str,
    view: ToolResultView,
    *,
    visible: bool,
    max_lines: int,
) -> str | None:
    if max_lines < 1 or not visible:
        return None
    text = view.rendered_text or view.result_text
    if not text:
        return None
    text = drop_tool_timing_tail_line(text.strip())
    if not text:
        return None
    return collapse_tool_output_preview(
        text,
        max_lines=max_lines,
        tail=prefers_tail_tool_output(tool_name),
    )


def _tool_state(status: ToolTranscriptStatus) -> ToolState:
    if status == "ok":
        return "completed"
    if status == "cancelled":
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


__all__ = [
    "ToolBodyVisibility",
    "ToolCommandResolver",
    "ToolCallSnapshot",
    "ToolCallView",
    "ToolResultView",
    "ToolTranscriptBlock",
    "ToolTranscriptProjector",
    "ToolTranscriptStatus",
    "ToolVerbResolver",
    "tool_block_to_record",
]
