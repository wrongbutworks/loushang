from __future__ import annotations

from typing import Any

from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, UserMessage
from loushang.coding.message import (
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
)
from loushang.coding.ui.tool_blocks import ToolTranscriptProjector
from loushang.coding.ui.transcript_projection import tool_block_to_record
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    DisplayRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


def session_history_records(
    session: Any,
    *,
    tool_definition_resolver: Any | None = None,
    max_tool_body_lines: int = 8,
) -> tuple[DisplayRecord, ...]:
    messages = _session_messages(session)
    if not messages:
        return ()
    tool_projector = ToolTranscriptProjector(
        tool_definition_resolver=tool_definition_resolver,
        max_body_lines=max_tool_body_lines,
    )
    records: list[DisplayRecord] = []
    for message in messages:
        record = _message_record(message, tool_projector=tool_projector)
        if record is not None:
            records.append(record)
    return tuple(records)


def _message_record(message: object, *, tool_projector: ToolTranscriptProjector) -> DisplayRecord | None:
    if isinstance(message, UserMessage):
        text = _text_from_content(message.content).strip()
        return UserPromptRecord(text) if text else None
    if isinstance(message, AssistantMessage):
        text = _text_from_content(message.content).strip()
        return AssistantMessageRecord(text, stable=True) if text else None
    if isinstance(message, ToolResultMessage):
        return tool_block_to_record(tool_projector.project_tool_result_message(message))
    if isinstance(message, BashExecutionMessage):
        return ToolExecutionRecord(
            name=f"bash {message.command}".strip(),
            state=_bash_state(message),
            elapsed_seconds=0.0,
            output=message.output,
            command=message.command,
            exit_code=message.exit_code,
            stderr="cancelled" if message.cancelled else "",
        )
    if isinstance(message, CompactionSummaryMessage):
        return ContextCompactionRecord(summary=message.summary, tokens_before=message.tokens_before)
    if isinstance(message, BranchSummaryMessage):
        return ContextCompactionRecord(summary=message.summary)
    if isinstance(message, CustomMessage) and message.display:
        text = _text_from_content(message.content).strip()
        return AssistantMessageRecord(text, stable=True) if text else None
    return None


def _session_messages(session: Any) -> list[object]:
    context_getter = getattr(session, "get_session_context", None)
    if callable(context_getter):
        try:
            context = context_getter()
        except Exception:
            context = None
        messages = _safe_getattr(context, "messages", None)
        if isinstance(messages, list):
            return list(messages)
    messages = _safe_getattr(session, "messages", None)
    if isinstance(messages, list):
        return list(messages)
    agent_state = _safe_getattr(_safe_getattr(session, "agent", None), "state", None)
    messages = _safe_getattr(agent_state, "messages", None)
    if isinstance(messages, list):
        return list(messages)
    return []


def _safe_getattr(target: Any, name: str, default: object) -> object:
    try:
        return getattr(target, name, default)
    except Exception:
        return default


def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, TextPart):
                parts.append(part.text)
        return "".join(parts)
    return ""


def _bash_state(message: BashExecutionMessage):
    if message.cancelled:
        return "cancelled"
    if message.exit_code not in (None, 0):
        return "failed"
    return "completed"


__all__ = ["session_history_records"]
