from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loushang.coding.ui.conversation_event_adapter import (
    CodingConversationEventAdapter,
)
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.tool_blocks import ToolTranscriptProjector
from loushang.coding.ui.transcript_projection import tool_block_to_record
from loushang.harnesstui.conversation.projection import ConversationProjector
from loushang.harnesstui.conversation.tool_transcript import (
    ToolCallSnapshot,
    ToolTranscriptBlock,
)
from loushang.tui.transcript import ToolExecutionRecord, UserPromptRecord

QueueReader = Callable[[], tuple[str, ...] | list[str]]
TraceFn = Callable[[str], None]


@dataclass(slots=True)
class ScreenCodingEventProjector:
    """Coding raw-event facade for the full-screen conversation target."""

    app: ScreenCodingTuiApp
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
            target=_ScreenProjectionTarget(self.app),
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


@dataclass(slots=True)
class _ScreenProjectionTarget:
    app: ScreenCodingTuiApp

    def run_started(self, *, start_time: Callable[[], float]) -> None:
        if not self.app.state.running:
            self.app.begin_run(started_at=start_time())

    def queues_updated(
        self,
        *,
        steers: tuple[str, ...],
        followups: tuple[str, ...],
    ) -> None:
        self.app.sync_queues(steers=steers, followups=followups)

    def user_message(self, text: str) -> None:
        text = text.strip()
        if text and not self.app.state.consume_pending_user_echo(text):
            self.app.state.records.append(UserPromptRecord(text))
            self.app.state.mark_records_changed()

    def assistant_started(self) -> None:
        self.app.begin_assistant()

    def assistant_delta(self, delta: str) -> None:
        self.app.append_assistant_chunk(delta)

    def assistant_finished(
        self,
        final_text: str,
        *,
        error_message: str | None,
        show_error: bool,
    ) -> None:
        # Screen commits the final assistant text even when the message reports an
        # error, then adds only errors that product policy says should be visible.
        self.app.end_assistant(final_text)
        if error_message is not None and show_error:
            self.app.add_error(error_message)

    def assistant_error(self, error_message: str) -> None:
        self.app.add_error(error_message)

    def tool_started(
        self,
        tool_call_id: str,
        snapshot: ToolCallSnapshot,
    ) -> None:
        self.app.state.upsert_tool_record(
            tool_call_id,
            ToolExecutionRecord(
                name=_tool_title(snapshot),
                state="running",
                elapsed_seconds=0.0,
            ),
        )

    def tool_finished(
        self,
        block: ToolTranscriptBlock,
        *,
        elapsed_seconds: float,
    ) -> None:
        self.app.state.upsert_tool_record(
            block.tool_call_id,
            tool_block_to_record(block, elapsed_seconds=elapsed_seconds),
        )

    def tool_result_message(self, block: ToolTranscriptBlock) -> None:
        # Full-screen mode already projects tool execution lifecycle records.
        del block

    def retry_started(
        self,
        *,
        attempt: int | None,
        max_attempts: int | None,
        delay_ms: int | float | None,
        error_message: str | None,
    ) -> None:
        self.app.set_status(
            f"retry {attempt}/{max_attempts} in {delay_ms}ms: {error_message}"
        )

    def compaction_started(self, *, reason: str | None) -> None:
        self.app.set_status(f"compact start: {reason}")

    def compaction_finished(
        self,
        *,
        error_message: str | None,
        summary: str,
        tokens_before: int | None,
    ) -> None:
        if error_message:
            self.app.set_status(f"compact error: {error_message}")
            return
        self.app.set_status("compact done")
        if summary:
            self.app.append_context_compaction_record(
                summary=summary,
                tokens_before=tokens_before,
            )


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
