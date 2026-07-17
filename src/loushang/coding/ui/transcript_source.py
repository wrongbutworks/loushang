from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from loushang.coding.ui.screen_state import ScreenCodingTuiState
from loushang.coding.ui.session_history import session_history_records
from loushang.harnesstui.conversation.source import TranscriptSnapshot, TranscriptSource
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    DisplayRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


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
        return _recent_assistant_texts(_active_window_records(self.state))


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
            merged_records = _merge_active_window_records(session_records, active_records)
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
        return _recent_assistant_texts(self.snapshot().records)


def _recent_assistant_texts(records: Iterable[DisplayRecord]) -> tuple[str, ...]:
    texts: list[str] = []
    for record in reversed(tuple(records)):
        if not isinstance(record, AssistantMessageRecord):
            continue
        if record.text.strip():
            texts.append(record.text)
    return tuple(texts)


def _active_window_records(state: ScreenCodingTuiState) -> tuple[DisplayRecord, ...]:
    records = tuple(state.records)
    assistant_draft = state.assistant_draft
    if assistant_draft is not None:
        return (*records, assistant_draft)
    return records


def _merge_active_window_records(
    session_records: tuple[DisplayRecord, ...],
    active_records: tuple[DisplayRecord, ...],
) -> tuple[DisplayRecord, ...]:
    if not active_records:
        return session_records
    overlap = _decorated_suffix_prefix_overlap(session_records, active_records)
    if overlap is None:
        return (*session_records, *active_records)
    session_start, active_start = overlap
    return (*session_records[:session_start], *active_records[active_start:])


def _decorated_suffix_prefix_overlap(
    left: tuple[DisplayRecord, ...],
    right: tuple[DisplayRecord, ...],
) -> tuple[int, int] | None:
    right_history_records = tuple(
        (index, record) for index, record in enumerate(right) if _history_projected_record(record)
    )
    max_overlap = min(len(left), len(right_history_records))
    for overlap_count in range(max_overlap, 0, -1):
        right_prefix = tuple(record for _, record in right_history_records[:overlap_count])
        if left[-overlap_count:] == right_prefix:
            return len(left) - overlap_count, 0
    return None


def _history_projected_record(record: DisplayRecord) -> bool:
    if isinstance(record, AssistantMessageRecord):
        return record.stable
    return isinstance(record, (UserPromptRecord, ToolExecutionRecord, ContextCompactionRecord))


__all__ = [
    "ActiveWindowTranscriptSource",
    "SessionTranscriptSource",
    "TranscriptSnapshot",
    "TranscriptSource",
]
