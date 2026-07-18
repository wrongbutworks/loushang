from __future__ import annotations

from loushang.coding.ui.screen_state import (
    ScreenCodingTuiState,
    ScreenTranscriptWindow,
)
from loushang.harnesstui.conversation.screen_state import (
    ActiveTranscriptWindow,
    ScreenConversationState,
)
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


def _state() -> ScreenCodingTuiState:
    return ScreenCodingTuiState(model_label="model", cwd="/repo", branch="main", session_label="session")


def test_coding_screen_state_names_are_shared_compatibility_aliases() -> None:
    assert ScreenCodingTuiState is ScreenConversationState
    assert ScreenTranscriptWindow is ActiveTranscriptWindow


def test_records_revision_tracks_record_appends_only_when_they_happen() -> None:
    state = _state()

    state.start_prompt("   ", started_at=0.0)
    state.end_assistant()
    state.add_error("")
    state.add_status("   ")
    assert state.records_revision == 0

    state.start_prompt("prompt", started_at=0.0)
    state.append_assistant_chunk("answer")
    state.end_assistant()
    state.complete_run(elapsed_seconds=1.0)
    assert state.records_revision == 3

    state.complete_run(elapsed_seconds=2.0)
    assert state.records_revision == 3

    state.add_error("failed")
    state.add_status("ready")
    assert state.records_revision == 5


def test_records_revision_tracks_replace_trim_and_manual_changes() -> None:
    state = _state()
    records = (UserPromptRecord("one"), AssistantMessageRecord("two"))

    state.replace_transcript_window(records)
    assert state.records_revision == 1

    state.replace_transcript_window(ScreenTranscriptWindow(records, evicted_prefix_record_count=4))
    state.trim_transcript_prefix(max_records=2)
    assert state.records_revision == 1

    assert state.trim_transcript_prefix(max_records=1) == 1
    assert state.records_revision == 2

    state.records.append(UserPromptRecord("manual"))
    state.mark_records_changed()
    assert state.records_revision == 3


def test_records_revision_tracks_tool_insert_and_changed_replacement() -> None:
    state = _state()
    running = ToolExecutionRecord(name="read", state="running", elapsed_seconds=0.1)
    completed = ToolExecutionRecord(name="read", state="completed", elapsed_seconds=0.2)

    state.upsert_tool_record("tool-1", running)
    assert state.records_revision == 1

    state.upsert_tool_record("tool-1", running)
    assert state.records_revision == 1

    state.upsert_tool_record("tool-1", completed)
    assert state.records_revision == 2


def test_records_revision_counts_each_append_in_compound_state_methods() -> None:
    state = _state()
    state.append_assistant_chunk("partial")

    state.abort(message="stopped", elapsed_seconds=1.0)

    assert state.records_revision == 2
