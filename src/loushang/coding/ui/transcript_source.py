from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loushang.coding.ui.session_history import session_history_records
from loushang.harnesstui.conversation.screen_state import ScreenConversationState
from loushang.harnesstui.conversation.source import (
    ActiveWindowTranscriptSource,
    TranscriptSnapshot,
    TranscriptSource,
    active_window_records,
    merge_history_and_active_records,
    recent_assistant_texts,
)


# Transcript reader sources intentionally separate three data shapes:
# - active window: bounded UI records plus current assistant draft.
# - session history: full materialized session projection.
# - session + live window: full history with active UI-only suffix records.
@dataclass(frozen=True, slots=True)
class SessionTranscriptSource:
    session: Any
    tool_definition_resolver: Any | None = None
    max_tool_body_lines: int = 8
    source_label: str = "Full transcript"
    active_window_state: ScreenConversationState | None = None

    def snapshot(self) -> TranscriptSnapshot:
        session_records = session_history_records(
            self.session,
            tool_definition_resolver=self.tool_definition_resolver,
            max_tool_body_lines=self.max_tool_body_lines,
        )
        records = session_records
        complete = True
        source_label = self.source_label
        if self.active_window_state is not None:
            active_records = active_window_records(self.active_window_state)
            merged_records = merge_history_and_active_records(
                session_records, active_records
            )
            if merged_records != session_records:
                records = merged_records
                complete = False
                source_label = f"{self.source_label} + live window"
        return TranscriptSnapshot(
            records=records,
            evicted_prefix_record_count=0,
            complete=complete,
            source_label=source_label,
        )

    def recent_assistant_texts(self) -> tuple[str, ...]:
        return recent_assistant_texts(self.snapshot().records)


__all__ = [
    "ActiveWindowTranscriptSource",
    "SessionTranscriptSource",
    "TranscriptSnapshot",
    "TranscriptSource",
]
