from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest

from loushang.harnesstui.conversation.source import (
    TranscriptSnapshot,
    TranscriptSource,
    merge_history_and_active_records,
    recent_assistant_texts,
)
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    DisplayRecord,
    StatusRecord,
    ToolExecutionRecord,
    UserPromptRecord,
    WorkedDividerRecord,
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


def test_recent_assistant_texts_filters_blank_messages_newest_first() -> None:
    records: tuple[DisplayRecord, ...] = (
        AssistantMessageRecord("  first  "),
        AssistantMessageRecord("   "),
        ToolExecutionRecord(name="read", state="completed", elapsed_seconds=0.1),
        AssistantMessageRecord("second", stable=False),
    )

    assert recent_assistant_texts(iter(records)) == ("second", "  first  ")


@pytest.mark.parametrize(
    ("record", "projected"),
    (
        (UserPromptRecord("question"), True),
        (AssistantMessageRecord("answer", stable=True), True),
        (AssistantMessageRecord("draft", stable=False), False),
        (
            ToolExecutionRecord(name="read", state="completed", elapsed_seconds=0.1),
            True,
        ),
        (ContextCompactionRecord("summary"), True),
        (WorkedDividerRecord(1.0), False),
        (StatusRecord("working"), False),
    ),
)
def test_merge_history_and_active_records_uses_only_projected_history_records(
    record: DisplayRecord, projected: bool
) -> None:
    decoration = StatusRecord("working")

    merged = merge_history_and_active_records(
        (record,),
        (record, decoration),
    )

    expected = (record, decoration) if projected else (record, record, decoration)
    assert merged == expected


def test_merge_history_and_active_records_returns_history_when_active_window_is_empty() -> (
    None
):
    history: tuple[DisplayRecord, ...] = (UserPromptRecord("question"),)

    merged = merge_history_and_active_records(history, ())

    assert merged is history


def test_merge_history_and_active_records_appends_unmatched_window() -> None:
    history: tuple[DisplayRecord, ...] = (UserPromptRecord("history"),)
    active: tuple[DisplayRecord, ...] = (UserPromptRecord("active"),)

    assert merge_history_and_active_records(history, active) == (*history, *active)


def test_merge_history_and_active_records_appends_ui_only_window() -> None:
    history: tuple[DisplayRecord, ...] = (UserPromptRecord("history"),)
    active: tuple[DisplayRecord, ...] = (
        WorkedDividerRecord(1.0),
        StatusRecord("working"),
        AssistantMessageRecord("draft", stable=False),
    )

    assert merge_history_and_active_records(history, active) == (*history, *active)


def test_merge_history_and_active_records_replaces_maximal_overlap_with_decorated_window() -> (
    None
):
    first_question = UserPromptRecord("first question")
    first_answer = AssistantMessageRecord("first answer")
    second_question = UserPromptRecord("second question")
    second_answer = AssistantMessageRecord("second answer")
    history: tuple[DisplayRecord, ...] = (
        first_question,
        first_answer,
        second_question,
        second_answer,
    )
    active: tuple[DisplayRecord, ...] = (
        second_question,
        WorkedDividerRecord(1.0),
        second_answer,
        AssistantMessageRecord("streaming draft", stable=False),
    )

    assert merge_history_and_active_records(history, active) == (
        first_question,
        first_answer,
        *active,
    )
