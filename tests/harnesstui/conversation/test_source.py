from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest

from loushang.harnesstui.conversation.source import TranscriptSnapshot, TranscriptSource
from loushang.tui.transcript import (
    AssistantMessageRecord,
    DisplayRecord,
    UserPromptRecord,
)


@dataclass(slots=True)
class _Source:
    records: tuple[DisplayRecord, ...]

    def snapshot(self) -> TranscriptSnapshot:
        return TranscriptSnapshot(records=self.records)

    def recent_assistant_texts(self) -> tuple[str, ...]:
        return tuple(
            record.text
            for record in reversed(self.records)
            if isinstance(record, AssistantMessageRecord) and record.text.strip()
        )


def _read_source(
    source: TranscriptSource,
) -> tuple[TranscriptSnapshot, tuple[str, ...]]:
    return source.snapshot(), source.recent_assistant_texts()


def test_transcript_snapshot_has_product_neutral_defaults() -> None:
    records: tuple[DisplayRecord, ...] = (
        UserPromptRecord("question"),
        AssistantMessageRecord("answer"),
    )

    snapshot = TranscriptSnapshot(records=records)

    assert snapshot.records is records
    assert snapshot.evicted_prefix_record_count == 0
    assert snapshot.complete is False
    assert snapshot.source_label == "Transcript window"


def test_transcript_snapshot_is_immutable() -> None:
    snapshot = TranscriptSnapshot(records=())

    with pytest.raises(FrozenInstanceError):
        snapshot.complete = True  # type: ignore[misc]


def test_transcript_source_is_a_structural_contract() -> None:
    source = _Source(
        (
            AssistantMessageRecord("first"),
            UserPromptRecord("next"),
            AssistantMessageRecord("second"),
        )
    )

    snapshot, recent_assistant_texts = _read_source(source)

    assert snapshot.records == source.records
    assert recent_assistant_texts == ("second", "first")
