from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from loushang.coding.ui.native_state import NativeCodingTuiState
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
        texts: list[str] = []
        for record in reversed(self.state.records):
            if not isinstance(record, AssistantMessageRecord):
                continue
            if record.text.strip():
                texts.append(record.text)
        return tuple(texts)


__all__ = ["ActiveWindowTranscriptSource", "TranscriptSnapshot", "TranscriptSource"]
