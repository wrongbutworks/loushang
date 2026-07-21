from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, TypeAlias

from loushang.agent.types import AgentToolResult
from loushang.harness.presentation import ToolDefinitionResolver, ToolRenderRuntime
from loushang.harness.tools.workspace.presentation import (
    render_tool_result_presentation,
)
from loushang.harnesstui.conversation.tool_transcript import (
    ToolCallSnapshot,
    ToolCallView,
    ToolResultView,
    ToolTranscriptBlock,
    ToolTranscriptProjectionBinding,
    ToolTranscriptStatus,
)
from loushang.harnesstui.conversation.tool_transcript import (
    ToolTranscriptProjector as NeutralToolTranscriptProjector,
)
from loushang.harnesstui.conversation.tool_transcript import (
    tool_block_to_record as project_neutral_tool_block,
)
from loushang.tui.transcript import ToolExecutionRecord

CodingToolTranscriptProjection: TypeAlias = ToolTranscriptProjectionBinding[
    Mapping[str, Any], object
]


@dataclass
class CodingToolTranscriptViewAdapter:
    """Adapt raw Coding tool events and messages to neutral transcript views."""

    tool_definition_resolver: ToolDefinitionResolver | None = None
    render_runtime: ToolRenderRuntime | None = None
    max_body_lines: int = 8

    def __post_init__(self) -> None:
        if self.render_runtime is None:
            self.render_runtime = ToolRenderRuntime()

    def call_id(self, event: Mapping[str, Any]) -> str:
        """Read a tool-call id without invoking presentation renderers."""

        return _tool_call_id(event)

    def message_id(self, message: object) -> str:
        """Read a tool-result message id without adapting its result body."""

        value = getattr(message, "tool_call_id", None)
        return value if isinstance(value, str) and value else ""

    def call_view(self, event: Mapping[str, Any]) -> ToolCallView:
        """Adapt a raw Coding tool-call event to a neutral view."""

        return ToolCallView(
            tool_call_id=self.call_id(event),
            tool_name=_tool_name(event),
            args=event.get("args"),
            rendered_text=self._render_event_text(event, expanded=False),
        )

    def result_view(
        self,
        event: Mapping[str, Any],
        snapshot: ToolCallSnapshot | None = None,
        tool_call_id: str | None = None,
    ) -> ToolResultView:
        """Adapt a raw Coding tool-result event to a neutral view."""

        result = _event_result(event)
        status = _result_status(event, result=result)
        event_tool_name = _tool_name(event)
        policy_tool_name = (
            snapshot.tool_name if snapshot is not None else event_tool_name
        )
        result_text = ""
        if _should_show_body(policy_tool_name, status):
            result_text = _fallback_result_text(
                result,
                max_lines=self.max_body_lines,
            )
        return ToolResultView(
            tool_call_id=(
                self.call_id(event) if tool_call_id is None else tool_call_id
            ),
            tool_name=event_tool_name,
            status=status,
            args=event.get("args"),
            result_text=result_text,
            rendered_text=self._render_event_text(event, expanded=False),
            details=_transcript_result_details(result),
            error_summary=_tool_error_summary(result),
        )

    def tool_result_message_view(self, message: object) -> ToolResultView:
        """Adapt a raw Coding tool-result message to a neutral view."""

        tool_name = str(getattr(message, "tool_name", "tool"))
        raw_tool_call_id = self.message_id(message)
        tool_call_id = raw_tool_call_id or tool_name
        event = {
            "type": "tool_execution_end",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "result": AgentToolResult(
                content=getattr(message, "content", None) or [],
                details=getattr(message, "details", None),
                terminate=bool(getattr(message, "terminate", False)),
            ),
            "is_error": bool(getattr(message, "is_error", False)),
        }
        return self.result_view(event, tool_call_id=tool_call_id)

    def _render_event_text(
        self,
        event: Mapping[str, Any],
        *,
        expanded: bool,
    ) -> str | None:
        if self.tool_definition_resolver is None or self.render_runtime is None:
            return None
        try:
            rendered = self.render_runtime.render_event(
                event,
                self.tool_definition_resolver,
                expanded=expanded,
            )
        except Exception:
            return None
        return _rendered_text(rendered)


def build_coding_tool_transcript_projection(
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    render_runtime: ToolRenderRuntime | None = None,
    max_body_lines: int = 8,
) -> CodingToolTranscriptProjection:
    """Compose Coding raw-view adaptation with neutral transcript projection."""

    adapter = CodingToolTranscriptViewAdapter(
        tool_definition_resolver=tool_definition_resolver,
        render_runtime=render_runtime,
        max_body_lines=max_body_lines,
    )
    return ToolTranscriptProjectionBinding(
        neutral_projector=NeutralToolTranscriptProjector(
            verb_resolver=_verb,
            body_visibility=_should_show_body,
            command_resolver=_command_for_transcript,
            max_body_lines=max_body_lines,
        ),
        call_id=adapter.call_id,
        message_id=adapter.message_id,
        call_view=adapter.call_view,
        result_view=adapter.result_view,
        tool_result_message_view=adapter.tool_result_message_view,
    )


def _event_result(event: Mapping[str, Any]) -> object:
    if event.get("type") == "tool_execution_update":
        return event.get("partial_result")
    return event.get("result")


def _tool_call_id(event: Mapping[str, Any]) -> str:
    value = event.get("tool_call_id")
    if isinstance(value, str) and value:
        return value
    return _tool_name(event) or "tool"


def _tool_name(event: Mapping[str, Any]) -> str:
    value = event.get("tool_name")
    return value if isinstance(value, str) and value else "tool"


def _rendered_text(rendered: object) -> str | None:
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


def _result_status(
    event: Mapping[str, Any],
    *,
    result: object,
) -> ToolTranscriptStatus:
    details = _transcript_result_details(result)
    if details:
        if details.get("timed_out") is True:
            return "timed_out"
        if details.get("cancelled") is True:
            return "cancelled"
    if bool(event.get("is_error", False)):
        return "error"
    if isinstance(result, AgentToolResult) and result.terminate:
        return "terminate"
    return "ok"


def _verb(tool_name: str, args: object | None) -> str:
    normalized = tool_name.lower()
    command = _command_from_args(args).lower()
    if any(
        part in normalized for part in ("read", "grep", "glob", "list", "ls", "search")
    ):
        return "Explored"
    if any(part in normalized for part in ("edit", "write", "patch")):
        return "Edited"
    if any(part in normalized for part in ("test", "lint", "ruff", "pytest")):
        return "Tested"
    if any(part in command for part in ("pytest", "ruff", "mypy", "lint", "test ")):
        return "Tested"
    if any(part in normalized for part in ("bash", "shell", "exec", "run")):
        return "Ran"
    return f"Used {tool_name}"


def _command_from_args(args: object | None) -> str:
    if isinstance(args, Mapping):
        command = args.get("command")
        if isinstance(command, str):
            return command
    return ""


def _command_for_transcript(
    tool_name: str, args: object | None, title: str
) -> str | None:
    return title if _verb(tool_name, args) in {"Ran", "Tested"} else None


def _should_show_body(
    tool_name: str,
    status: ToolTranscriptStatus,
) -> bool:
    if status != "ok":
        return False
    normalized = tool_name.lower()
    return any(
        part in normalized
        for part in (
            "bash",
            "shell",
            "exec",
            "run",
            "grep",
            "find",
            "ls",
            "test",
            "lint",
            "ruff",
            "pytest",
        )
    )


def _fallback_result_text(result: object, *, max_lines: int) -> str:
    if not isinstance(result, AgentToolResult):
        return ""
    return render_tool_result_presentation(
        result.content,
        _transcript_result_details(result),
        max_collapsed_lines=max_lines,
    ).collapsed


def _transcript_result_details(result: object) -> Mapping[str, Any]:
    if not isinstance(result, AgentToolResult):
        return {}
    try:
        details = result.transcript_details()
    except Exception:
        return {}
    return details if isinstance(details, Mapping) else {}


def _tool_error_summary(result: object) -> str | None:
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


def tool_block_to_record(
    block: ToolTranscriptBlock,
    *,
    elapsed_seconds: float = 0.0,
) -> ToolExecutionRecord:
    """Preserve Coding's command-label policy at the product edge."""

    if block.command is None and block.verb in {"Ran", "Tested"}:
        block = replace(block, command=block.title)
    return project_neutral_tool_block(
        block,
        elapsed_seconds=elapsed_seconds,
    )


__all__ = [
    "CodingToolTranscriptProjection",
    "CodingToolTranscriptViewAdapter",
    "build_coding_tool_transcript_projection",
    "tool_block_to_record",
]
