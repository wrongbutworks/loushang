from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from loushang.tui.transcript import DisplayRecord


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


__all__ = ["TranscriptSnapshot", "TranscriptSource"]
