from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loushang.coding.presentation.tui.events import (
    CodingConversationEventAdapter,
)
from loushang.coding.presentation.tui.tool_transcript import (
    ToolTranscriptProjector,
    tool_block_to_record,
)
from loushang.harnesstui.conversation.projection import ConversationProjector
from loushang.harnesstui.conversation.screen_target import (
    ScreenConversationProjectionPort,
    ScreenConversationProjectionTarget,
)
from loushang.harnesstui.conversation.tool_transcript import (
    ToolCallSnapshot,
    ToolTranscriptBlock,
)

QueueReader = Callable[[], tuple[str, ...] | list[str]]
TraceFn = Callable[[str], None]


@dataclass(slots=True)
class ScreenCodingEventProjector:
    """Coding raw-event facade for the full-screen conversation target."""

    app: ScreenConversationProjectionPort
    tool_definition_resolver: Any | None = None
    max_tool_body_lines: int = 8
    read_pending_steers: QueueReader = tuple
    read_pending_followups: QueueReader = tuple
    now: Callable[[], float] = time.monotonic
    _tool_projector: ToolTranscriptProjector = field(init=False, repr=False)
    _projection: ConversationProjector = field(init=False, repr=False)
    _adapter: CodingConversationEventAdapter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._tool_projector = ToolTranscriptProjector(
            tool_definition_resolver=self.tool_definition_resolver,
            max_body_lines=self.max_tool_body_lines,
        )
        self._projection = ConversationProjector(
            target=ScreenConversationProjectionTarget(
                self.app,
                tool_title_resolver=_tool_title,
                tool_record_projector=tool_block_to_record,
                status_copy=_CodingScreenProjectionStatusCopy(),
            ),
            tool_projector=self._tool_projector.neutral_projector,
            now=self.now,
            track_rendered_tool_results=False,
        )
        self._adapter = CodingConversationEventAdapter(
            self._projection,
            self._tool_projector,
            read_pending_steers=self.read_pending_steers,
            read_pending_followups=self.read_pending_followups,
            recover_tool_updates=True,
            project_tool_result_messages=False,
            require_assistant_message_for_delta=True,
            project_run_starts=True,
            project_queue_updates=True,
            project_user_messages=True,
            project_assistant_error_text=True,
            project_compaction_details=True,
        )

    def handle(self, event: dict[str, Any]) -> None:
        self._adapter.handle(event)


@dataclass(frozen=True, slots=True)
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


__all__ = ["ScreenCodingEventProjector"]
