from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loushang.coding.ui.screen_state import ScreenCodingTuiState
from loushang.coding.ui.session_history import session_history_records
from loushang.harnesstui.conversation.source import (
    TranscriptSnapshot,
    TranscriptSource,
    merge_history_and_active_records,
    recent_assistant_texts,
)
from loushang.tui.transcript import DisplayRecord


# Transcript reader sources intentionally separate three data shapes:
# - active window: bounded UI records plus current assistant draft.
# - session history: full materialized session projection.
# - session + live window: full history with active UI-only suffix records.
@dataclass(frozen=True, slots=True)
class ActiveWindowTranscriptSource:
    state: ScreenCodingTuiState

    def snapshot(self) -> TranscriptSnapshot:
        return TranscriptSnapshot(
            records=_active_window_records(self.state),
            evicted_prefix_record_count=max(0, self.state.evicted_prefix_record_count),
            complete=False,
            source_label="Transcript window",
        )

    def recent_assistant_texts(self) -> tuple[str, ...]:
        return recent_assistant_texts(_active_window_records(self.state))


@dataclass(frozen=True, slots=True)
class SessionTranscriptSource:
    session: Any
    tool_definition_resolver: Any | None = None
    max_tool_body_lines: int = 8
    source_label: str = "Full transcript"
    active_window_state: ScreenCodingTuiState | None = None

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
            active_records = _active_window_records(self.active_window_state)
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


def _active_window_records(state: ScreenCodingTuiState) -> tuple[DisplayRecord, ...]:
    records = tuple(state.records)
    assistant_draft = state.assistant_draft
    if assistant_draft is not None:
        return (*records, assistant_draft)
    return records


__all__ = [
    "ActiveWindowTranscriptSource",
    "SessionTranscriptSource",
    "TranscriptSnapshot",
    "TranscriptSource",
]
