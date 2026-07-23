from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from loushang.coding.session_manager import SessionManager
from loushang.harness.presentation import ToolDefinitionResolver
from loushang.harnesstui.conversation.agent_binding import (
    agent_tool_block_to_record,
    build_agent_tool_transcript_projection,
    project_agent_conversation_history,
)
from loushang.tui.transcript import DisplayRecord


def session_history_records(
    branch_items: Iterable[object],
    *,
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    max_tool_body_lines: int = 8,
) -> tuple[DisplayRecord, ...]:
    transcript_items = tuple(branch_items)
    if not transcript_items:
        return ()
    tool_projector = build_agent_tool_transcript_projection(
        tool_definition_resolver=tool_definition_resolver,
        max_body_lines=max_tool_body_lines,
    )
    return project_agent_conversation_history(
        transcript_items,
        tool_result_projector=lambda message: agent_tool_block_to_record(
            tool_projector.project_tool_result_message(message)
        ),
    )


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


__all__ = [
    "load_persisted_session_history_records",
    "session_history_records",
]
