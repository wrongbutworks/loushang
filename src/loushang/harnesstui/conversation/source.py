from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    DisplayRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


@dataclass(frozen=True, slots=True)
class TranscriptSnapshot:
    """One immutable conversation view consumed by transcript interactions."""

    records: tuple[DisplayRecord, ...]
    evicted_prefix_record_count: int = 0
    complete: bool = False
    source_label: str = "Transcript window"


class TranscriptSource(Protocol):
    """Product-neutral source for a transcript interaction."""

    def snapshot(self) -> TranscriptSnapshot: ...

    def recent_assistant_texts(self) -> tuple[str, ...]: ...


def recent_assistant_texts(records: Iterable[DisplayRecord]) -> tuple[str, ...]:
    """Return non-empty assistant messages in newest-first order."""

    texts: list[str] = []
    for record in reversed(tuple(records)):
        if not isinstance(record, AssistantMessageRecord):
            continue
        if record.text.strip():
            texts.append(record.text)
    return tuple(texts)


def merge_history_and_active_records(
    history_records: tuple[DisplayRecord, ...],
    active_records: tuple[DisplayRecord, ...],
) -> tuple[DisplayRecord, ...]:
    """Merge a projected history with its decorated active-window suffix."""

    if not active_records:
        return history_records
    history_start = _decorated_suffix_prefix_overlap(history_records, active_records)
    if history_start is None:
        return (*history_records, *active_records)
    return (*history_records[:history_start], *active_records)


def _is_history_projected_record(record: DisplayRecord) -> bool:
    """Whether a display record can originate from materialized history."""

    if isinstance(record, AssistantMessageRecord):
        return record.stable
    return isinstance(
        record, (UserPromptRecord, ToolExecutionRecord, ContextCompactionRecord)
    )


def _decorated_suffix_prefix_overlap(
    history_records: tuple[DisplayRecord, ...],
    active_records: tuple[DisplayRecord, ...],
) -> int | None:
    active_history_records = tuple(
        record for record in active_records if _is_history_projected_record(record)
    )
    max_overlap = min(len(history_records), len(active_history_records))
    for overlap_count in range(max_overlap, 0, -1):
        if history_records[-overlap_count:] == active_history_records[:overlap_count]:
            return len(history_records) - overlap_count
    return None


__all__ = [
    "TranscriptSnapshot",
    "TranscriptSource",
    "merge_history_and_active_records",
    "recent_assistant_texts",
]
