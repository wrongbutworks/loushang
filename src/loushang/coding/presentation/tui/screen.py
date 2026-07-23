from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from loushang.coding.presentation.tui.tool_transcript import (
    CodingToolTranscriptProjection,
    build_coding_tool_transcript_projection,
    tool_block_to_record,
)
from loushang.harnesstui.conversation.projection import (
    ConversationProjectionBinding,
    SessionConversationEventAdapter,
)
from loushang.harnesstui.conversation.runtime_view import StringQueueReader
from loushang.harnesstui.conversation.screen_target import (
    ScreenConversationProjectionPort,
    build_screen_conversation_projection,
)
from loushang.harnesstui.conversation.tool_transcript import (
    ToolCallSnapshot,
    ToolTranscriptBlock,
)


def build_screen_coding_event_projection(
    app: ScreenConversationProjectionPort,
    tool_definition_resolver: Any | None = None,
    max_tool_body_lines: int = 8,
    read_pending_steers: StringQueueReader = tuple,
    read_pending_followups: StringQueueReader = tuple,
    now: Callable[[], float] = time.monotonic,
) -> ConversationProjectionBinding[dict[str, Any]]:
    """Build the Coding event adapter over a shared screen projection."""

    tool_projection: CodingToolTranscriptProjection = (
        build_coding_tool_transcript_projection(
            tool_definition_resolver=tool_definition_resolver,
            max_body_lines=max_tool_body_lines,
        )
    )
    return build_screen_conversation_projection(
        app,
        tool_projector=tool_projection.neutral_projector,
        tool_title_resolver=_tool_title,
        tool_record_projector=tool_block_to_record,
        status_copy=_CodingScreenProjectionStatusCopy(),
        event_handler_factory=lambda projection: (
            SessionConversationEventAdapter(
                projection,
                tool_projection,
                read_pending_steers=read_pending_steers,
                read_pending_followups=read_pending_followups,
                project_tool_result_messages=False,
            ).handle
        ),
        now=now,
    )


class _CodingScreenProjectionStatusCopy:
    def retry_status(
        self,
        *,
        attempt: int | None,
        max_attempts: int | None,
        delay_ms: int | float | None,
        error_message: str | None,
    ) -> str:
        return f"retry {attempt}/{max_attempts} in {delay_ms}ms: {error_message}"

    def compaction_started_status(self, *, reason: str | None) -> str:
        return f"compact start: {reason}"

    def compaction_finished_status(
        self,
        *,
        error_message: str | None,
    ) -> str:
        if error_message:
            return f"compact error: {error_message}"
        return "compact done"


def _tool_title(snapshot: ToolCallSnapshot) -> str:
    if snapshot.rendered_call_text:
        return snapshot.rendered_call_text.splitlines()[0].strip()
    block = ToolTranscriptBlock(
        tool_call_id="tool",
        tool_name=snapshot.tool_name,
        status="running",
        verb="Ran",
        title=snapshot.tool_name,
    )
    return tool_block_to_record(block).name


__all__ = ["build_screen_coding_event_projection"]
