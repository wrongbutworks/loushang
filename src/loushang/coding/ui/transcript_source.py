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

    def snapshot(self) -> TranscriptSnapshot:
        return TranscriptSnapshot(
            records=session_history_records(
                self.session,
                tool_definition_resolver=self.tool_definition_resolver,
                max_tool_body_lines=self.max_tool_body_lines,
            ),
            evicted_prefix_record_count=0,
            complete=True,
            source_label=self.source_label,
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


__all__ = [
    "ActiveWindowTranscriptSource",
    "SessionTranscriptSource",
    "TranscriptSnapshot",
    "TranscriptSource",
]
