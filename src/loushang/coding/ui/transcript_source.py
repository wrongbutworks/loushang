from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from loushang.coding.ui.native_state import NativeCodingTuiState
from loushang.coding.ui.session_history import session_history_records
from loushang.tui.transcript import AssistantMessageRecord, DisplayRecord


@dataclass(frozen=True, slots=True)
class TranscriptSnapshot:
    records: tuple[DisplayRecord, ...]
    evicted_prefix_record_count: int = 0
    complete: bool = False
    source_label: str = "Transcript window"


class TranscriptSource(Protocol):
    def snapshot(self) -> TranscriptSnapshot: ...

    def recent_assistant_texts(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class ActiveWindowTranscriptSource:
    state: NativeCodingTuiState

    def snapshot(self) -> TranscriptSnapshot:
        return TranscriptSnapshot(
            records=tuple(self.state.records),
            evicted_prefix_record_count=max(0, self.state.evicted_prefix_record_count),
            complete=False,
            source_label="Transcript window",
        )

    def recent_assistant_texts(self) -> tuple[str, ...]:
        return _recent_assistant_texts(self.state.records)


@dataclass(frozen=True, slots=True)
class SessionTranscriptSource:
    session: Any
    tool_definition_resolver: Any | None = None
    max_tool_body_lines: int = 8
    source_label: str = "Full transcript"
    active_window_state: NativeCodingTuiState | None = None

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
            active_records = tuple(self.active_window_state.records)
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


def _merge_active_window_records(
    session_records: tuple[DisplayRecord, ...],
    active_records: tuple[DisplayRecord, ...],
) -> tuple[DisplayRecord, ...]:
    if not active_records:
        return session_records
    overlap_count = _suffix_prefix_overlap_count(session_records, active_records)
    if overlap_count == len(active_records):
        return session_records
    return (*session_records, *active_records[overlap_count:])


def _suffix_prefix_overlap_count(
    left: tuple[DisplayRecord, ...],
    right: tuple[DisplayRecord, ...],
) -> int:
    max_overlap = min(len(left), len(right))
    for overlap_count in range(max_overlap, 0, -1):
        if left[-overlap_count:] == right[:overlap_count]:
            return overlap_count
    return 0


__all__ = [
    "ActiveWindowTranscriptSource",
    "SessionTranscriptSource",
    "TranscriptSnapshot",
    "TranscriptSource",
]
