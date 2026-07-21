from __future__ import annotations

from collections.abc import Iterable
from functools import partial
from pathlib import Path

from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, UserMessage
from loushang.coding.presentation.tui.tool_transcript import (
    CodingToolTranscriptProjection,
    build_coding_tool_transcript_projection,
    tool_block_to_record,
)
from loushang.coding.session_manager import SessionManager
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
)
from loushang.harness.conversation import CommandExecutionRecord
from loushang.harness.presentation import ToolDefinitionResolver
from loushang.harnesstui.conversation.history import (
    ConversationHistoryProjector,
    HistoryRecordDisposition,
    project_context_branch_summary_payload,
    project_context_compaction_payload,
)
from loushang.tui.transcript import (
    AssistantMessageRecord,
    DisplayRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)

TUI_TRANSCRIPT_DISPOSITIONS: dict[str, HistoryRecordDisposition] = {
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
    branch_items: Iterable[object],
    *,
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    max_tool_body_lines: int = 8,
) -> tuple[DisplayRecord, ...]:
    transcript_items = tuple(branch_items)
    if not transcript_items:
        return ()
    tool_projector = build_coding_tool_transcript_projection(
        tool_definition_resolver=tool_definition_resolver,
        max_body_lines=max_tool_body_lines,
    )
    message_projector = partial(_message_record, tool_projector=tool_projector)
    return ConversationHistoryProjector(
        dispositions=TUI_TRANSCRIPT_DISPOSITIONS,
        payload_projectors={
            AGENT_MESSAGE_KIND: message_projector,
            COMMAND_EXECUTION_KIND: _command_record,
            CONTEXT_COMPACTION_CHECKPOINT_KIND: project_context_compaction_payload,
            CONTEXT_BRANCH_SUMMARY_KIND: project_context_branch_summary_payload,
            APPLICATION_MESSAGE_KIND: message_projector,
        },
        fallback_projector=message_projector,
    ).project_items(transcript_items)


async def load_persisted_session_history_records(
    session_file: str | Path,
    *,
    tool_definition_resolver: ToolDefinitionResolver | None = None,
) -> tuple[DisplayRecord, ...]:
    """Load a persisted Coding session into terminal transcript records."""

    manager = await SessionManager.load(Path(session_file).expanduser().resolve())
    return session_history_records(
        manager.get_branch(),
        tool_definition_resolver=tool_definition_resolver,
    )


def _message_record(
    message: object,
    *,
    tool_projector: CodingToolTranscriptProjection,
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


def _command_record(payload: object) -> ToolExecutionRecord | None:
    if not isinstance(payload, CommandExecutionRecord):
        return None
    command = payload
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


__all__ = [
    "load_persisted_session_history_records",
    "session_history_records",
]
