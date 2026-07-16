from __future__ import annotations

from typing import Any

from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, UserMessage
from loushang.coding.ui.tool_blocks import ToolTranscriptProjector
from loushang.coding.ui.transcript_projection import tool_block_to_record
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    APPLICATION_MESSAGE_KIND,
    COMMAND_EXECUTION_KIND,
    CONTEXT_BRANCH_SUMMARY_KIND,
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
    CONVERSATION_METADATA_PATCH_KIND,
    EXTENSION_DATA_KIND,
    MODEL_SELECTION_KIND,
    RECORD_ANNOTATION_PATCH_KIND,
    STANDARD_AGENT_TRANSCRIPT_KINDS,
    THINKING_SELECTION_KIND,
    ApplicationMessage,
    BranchContextSummary,
    ContextCompactionCheckpoint,
)
from loushang.harness.conversation import CommandExecutionRecord, ConversationRecord
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    DisplayRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)

TUI_TRANSCRIPT_DISPOSITIONS = {
    AGENT_MESSAGE_KIND: "render",
    THINKING_SELECTION_KIND: "state-only",
    MODEL_SELECTION_KIND: "state-only",
    COMMAND_EXECUTION_KIND: "render",
    CONTEXT_COMPACTION_CHECKPOINT_KIND: "render",
    CONTEXT_BRANCH_SUMMARY_KIND: "render",
    APPLICATION_MESSAGE_KIND: "render",
    EXTENSION_DATA_KIND: "hidden",
    RECORD_ANNOTATION_PATCH_KIND: "metadata-only",
    CONVERSATION_METADATA_PATCH_KIND: "metadata-only",
}
if set(TUI_TRANSCRIPT_DISPOSITIONS) != set(STANDARD_AGENT_TRANSCRIPT_KINDS):
    raise RuntimeError("TUI transcript dispositions must cover every standard kind")


def session_history_records(
    session: Any,
    *,
    tool_definition_resolver: Any | None = None,
    max_tool_body_lines: int = 8,
) -> tuple[DisplayRecord, ...]:
    transcript_items = _session_transcript_items(session)
    if not transcript_items:
        return ()
    tool_projector = ToolTranscriptProjector(
        tool_definition_resolver=tool_definition_resolver,
        max_body_lines=max_tool_body_lines,
    )
    records: list[DisplayRecord] = []
    for item in transcript_items:
        record = _transcript_record(item, tool_projector=tool_projector)
        if record is not None:
            records.append(record)
    return tuple(records)


def _transcript_record(
    item: object, *, tool_projector: ToolTranscriptProjector
) -> DisplayRecord | None:
    if isinstance(item, ConversationRecord):
        disposition = TUI_TRANSCRIPT_DISPOSITIONS.get(item.kind)
        if disposition is not None and disposition != "render":
            return None
        if item.kind == AGENT_MESSAGE_KIND:
            return _message_record(item.payload, tool_projector=tool_projector)
        if item.kind == COMMAND_EXECUTION_KIND and isinstance(
            item.payload, CommandExecutionRecord
        ):
            return _command_record(item.payload)
        if item.kind == CONTEXT_COMPACTION_CHECKPOINT_KIND and isinstance(
            item.payload, ContextCompactionCheckpoint
        ):
            return ContextCompactionRecord(
                summary=item.payload.summary,
                tokens_before=item.payload.tokens_before,
            )
        if item.kind == CONTEXT_BRANCH_SUMMARY_KIND and isinstance(
            item.payload, BranchContextSummary
        ):
            return ContextCompactionRecord(summary=item.payload.summary)
        if item.kind == APPLICATION_MESSAGE_KIND and isinstance(
            item.payload, ApplicationMessage
        ):
            if not item.payload.display:
                return None
            text = _text_from_content(item.payload.content).strip()
            return AssistantMessageRecord(text, stable=True) if text else None
        return None
    return _message_record(item, tool_projector=tool_projector)


def _message_record(
    message: object, *, tool_projector: ToolTranscriptProjector
) -> DisplayRecord | None:
    if isinstance(message, UserMessage):
        text = _text_from_content(message.content).strip()
        return UserPromptRecord(text) if text else None
    if isinstance(message, AssistantMessage):
        text = _text_from_content(message.content).strip()
        return AssistantMessageRecord(text, stable=True) if text else None
    if isinstance(message, ToolResultMessage):
        return tool_block_to_record(tool_projector.project_tool_result_message(message))
    if isinstance(message, ApplicationMessage) and message.display:
        text = _text_from_content(message.content).strip()
        return AssistantMessageRecord(text, stable=True) if text else None
    return None


def _session_transcript_items(session: Any) -> list[object]:
    manager = _safe_getattr(session, "session_manager", None)
    get_branch = _safe_getattr(manager, "get_branch", None)
    if callable(get_branch):
        try:
            records = get_branch()
        except Exception:
            records = None
        if isinstance(records, list):
            return list(records)
    context_getter = getattr(session, "get_session_context", None)
    if callable(context_getter):
        try:
            context = context_getter()
        except Exception:
            context = None
        messages = _safe_getattr(context, "messages", None)
        if isinstance(messages, list | tuple):
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


def _command_record(command: CommandExecutionRecord) -> ToolExecutionRecord:
    return ToolExecutionRecord(
        name=f"bash {command.command}".strip(),
        state=_bash_state(command),
        elapsed_seconds=0.0,
        output=command.output,
        command=command.command,
        exit_code=command.exit_code,
        stderr="cancelled" if command.cancelled else "",
    )


def _bash_state(command: CommandExecutionRecord):
    if command.cancelled:
        return "cancelled"
    if command.exit_code not in (None, 0):
        return "failed"
    return "completed"


__all__ = ["session_history_records"]
