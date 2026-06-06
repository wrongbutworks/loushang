from __future__ import annotations

from loushang.coding.ui.native_state import NativeCodingTuiState
from loushang.coding.ui.transcript_source import ActiveWindowTranscriptSource
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


def test_active_window_transcript_source_returns_snapshot_metadata() -> None:
    state = NativeCodingTuiState(model_label="model", cwd="/tmp/project", branch=None, session_label=None)
    state.replace_transcript_window(
        (
            UserPromptRecord("hello"),
            AssistantMessageRecord("answer"),
        ),
        evicted_prefix_record_count=3,
    )

    snapshot = ActiveWindowTranscriptSource(state).snapshot()

    assert snapshot.records == tuple(state.records)
    assert snapshot.evicted_prefix_record_count == 3
    assert snapshot.complete is False
    assert snapshot.source_label == "Transcript window"


def test_active_window_transcript_source_recent_assistant_texts_are_filtered_newest_first() -> None:
    state = NativeCodingTuiState(model_label="model", cwd="/tmp/project", branch=None, session_label=None)
    state.records.extend(
        [
            AssistantMessageRecord("first"),
            AssistantMessageRecord(""),
            ToolExecutionRecord(name="read", state="completed", elapsed_seconds=0.1),
            AssistantMessageRecord("second"),
        ]
    )

    assert ActiveWindowTranscriptSource(state).recent_assistant_texts() == ("second", "first")
