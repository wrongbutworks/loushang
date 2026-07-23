from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, TypeAlias

from loushang.agent.types import AgentToolResult
from loushang.harness.presentation import ToolDefinitionResolver, ToolRenderRuntime
from loushang.harness.tools.workspace.presentation import (
    render_tool_result_presentation,
)
from loushang.harnesstui.conversation.tool_transcript import (
    ToolTranscriptBlock,
    ToolTranscriptProjectionBinding,
    build_mapping_tool_transcript_projection,
)
from loushang.harnesstui.conversation.tool_transcript import (
    tool_block_to_record as project_neutral_tool_block,
)
from loushang.tui.transcript import ToolExecutionRecord

CodingToolTranscriptProjection: TypeAlias = ToolTranscriptProjectionBinding[
    Mapping[str, Any], object
]


def build_coding_tool_transcript_projection(
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    render_runtime: ToolRenderRuntime | None = None,
    max_body_lines: int = 8,
) -> CodingToolTranscriptProjection:
    """Bind Agent tool results and optional Coding renderers to HarnessTUI."""

    resolved_runtime = render_runtime or ToolRenderRuntime()
    render_event = (
        None
        if tool_definition_resolver is None
        else lambda event, expanded: _render_event_text(
            event,
            expanded=expanded,
            tool_definition_resolver=tool_definition_resolver,
            render_runtime=resolved_runtime,
        )
    )
    return build_mapping_tool_transcript_projection(
        result_text=_result_text,
        result_details=_result_details,
        result_terminated=lambda result: (
            isinstance(result, AgentToolResult) and result.terminate
        ),
        error_summary=_error_summary,
        message_event=_message_event,
        render_event_text=render_event,
        max_body_lines=max_body_lines,
    )


def _message_event(message: object) -> Mapping[str, Any]:
    tool_name = str(getattr(message, "tool_name", "tool"))
    tool_call_id = getattr(message, "tool_call_id", None)
    return {
        "type": "tool_execution_end",
        "tool_call_id": (
            tool_call_id
            if isinstance(tool_call_id, str) and tool_call_id
            else tool_name
        ),
        "tool_name": tool_name,
        "result": AgentToolResult(
            content=getattr(message, "content", None) or [],
            details=getattr(message, "details", None),
            terminate=bool(getattr(message, "terminate", False)),
        ),
        "is_error": bool(getattr(message, "is_error", False)),
    }


def _result_text(result: object, max_lines: int) -> str:
    if not isinstance(result, AgentToolResult):
        return ""
    return render_tool_result_presentation(
        result.content,
        _result_details(result),
        max_collapsed_lines=max_lines,
    ).collapsed


def _result_details(result: object) -> Mapping[str, Any]:
    if not isinstance(result, AgentToolResult):
        return {}
    try:
        details = result.transcript_details()
    except Exception:
        return {}
    return details if isinstance(details, Mapping) else {}


def _error_summary(result: object) -> str | None:
    content = getattr(result, "content", None)
    if not isinstance(content, list):
        return None
    for part in content:
        text = getattr(part, "text", None)
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            summary = line.strip()
            if summary:
                return summary if len(summary) <= 160 else summary[:157] + "..."
    return None


def _render_event_text(
    event: Mapping[str, Any],
    *,
    expanded: bool,
    tool_definition_resolver: ToolDefinitionResolver,
    render_runtime: ToolRenderRuntime,
) -> str | None:
    try:
        rendered = render_runtime.render_event(
            event,
            tool_definition_resolver,
            expanded=expanded,
        )
    except Exception:
        return None
    if isinstance(rendered, str):
        return rendered
    if isinstance(rendered, Mapping):
        plain = rendered.get("plain_text")
        if isinstance(plain, str):
            return plain
        text = rendered.get("text")
        if isinstance(text, str):
            return text
    return None


def tool_block_to_record(
    block: ToolTranscriptBlock,
    *,
    elapsed_seconds: float = 0.0,
) -> ToolExecutionRecord:
    """Preserve Coding's command-label policy at the Product edge."""

    if block.command is None and block.verb in {"Ran", "Tested"}:
        block = replace(block, command=block.title)
    return project_neutral_tool_block(
        block,
        elapsed_seconds=elapsed_seconds,
    )


__all__ = [
    "CodingToolTranscriptProjection",
    "build_coding_tool_transcript_projection",
    "tool_block_to_record",
]
