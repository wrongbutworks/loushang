from __future__ import annotations

from dataclasses import dataclass

from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
from loushang.coding.ui.native_state import NativeCodingTuiState
from loushang.coding.ui.transcript_source import (
    ActiveWindowTranscriptSource,
    SessionTranscriptSource,
)
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


@dataclass(slots=True)
class _Session:
    messages: list[object]


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


def test_session_transcript_source_returns_complete_session_snapshot() -> None:
    session = _Session(
        messages=[
            UserMessage(role="user", content=[TextPart(type="text", text="full question")], timestamp=1.0),
            _assistant_message("full answer", timestamp=2.0),
        ]
    )

    snapshot = SessionTranscriptSource(session).snapshot()

    assert snapshot.complete is True
    assert snapshot.evicted_prefix_record_count == 0
    assert snapshot.source_label == "Full transcript"
    assert snapshot.records == (
        UserPromptRecord("full question"),
        AssistantMessageRecord("full answer", stable=True),
    )


def test_session_transcript_source_recent_assistant_texts_are_filtered_newest_first() -> None:
    session = _Session(
        messages=[
            _assistant_message("first", timestamp=1.0),
            _assistant_message("   ", timestamp=2.0),
            UserMessage(role="user", content=[TextPart(type="text", text="next")], timestamp=3.0),
            _assistant_message("second", timestamp=4.0),
        ]
    )

    assert SessionTranscriptSource(session).recent_assistant_texts() == ("second", "first")


def test_session_transcript_source_merges_live_active_window_records() -> None:
    session = _Session(
        messages=[
            UserMessage(role="user", content=[TextPart(type="text", text="full question")], timestamp=1.0),
            _assistant_message("full answer", timestamp=2.0),
        ]
    )
    state = NativeCodingTuiState(model_label="model", cwd="/tmp/project", branch=None, session_label=None)
    state.replace_transcript_window(
        (
            UserPromptRecord("full question"),
            AssistantMessageRecord("full answer", stable=True),
            ToolExecutionRecord(name="bash run-tests", state="running", elapsed_seconds=0.1, output="live output"),
        )
    )
    state.begin_run(started_at=3.0)

    snapshot = SessionTranscriptSource(session, active_window_state=state).snapshot()

    assert snapshot.complete is False
    assert snapshot.source_label == "Full transcript + live window"
    assert snapshot.records == (
        UserPromptRecord("full question"),
        AssistantMessageRecord("full answer", stable=True),
        ToolExecutionRecord(name="bash run-tests", state="running", elapsed_seconds=0.1, output="live output"),
    )


def test_session_transcript_source_merges_live_assistant_draft() -> None:
    session = _Session(
        messages=[
            UserMessage(role="user", content=[TextPart(type="text", text="full question")], timestamp=1.0),
            _assistant_message("full answer", timestamp=2.0),
        ]
    )
    state = NativeCodingTuiState(model_label="model", cwd="/tmp/project", branch=None, session_label=None)
    state.replace_transcript_window(
        (
            UserPromptRecord("full question"),
            AssistantMessageRecord("full answer", stable=True),
        )
    )
    state.begin_run(started_at=3.0)
    state.append_assistant_chunk("streaming draft")

    snapshot = SessionTranscriptSource(session, active_window_state=state).snapshot()

    assert snapshot.complete is False
    assert snapshot.source_label == "Full transcript + live window"
    assert snapshot.records == (
        UserPromptRecord("full question"),
        AssistantMessageRecord("full answer", stable=True),
        AssistantMessageRecord("streaming draft", stable=False),
    )


def _assistant_message(text: str, *, timestamp: float) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text=text)],
        api="openai",
        provider="moonshot",
        model="kimi",
        response_id=None,
        usage=Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}),
        stop_reason="stop",
        error_message=None,
        timestamp=timestamp,
    )
