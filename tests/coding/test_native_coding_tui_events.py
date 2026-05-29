from __future__ import annotations

from types import SimpleNamespace

from loushang.agent import AgentToolResult
from loushang.ai import TextPart, UserMessage
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


def _assistant(text: str = "", *, stop_reason: str = "stop", error_message: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        role="assistant",
        content=[TextPart(type="text", text=text)] if text else [],
        stop_reason=stop_reason,
        error_message=error_message,
    )


def test_native_event_projector_streams_assistant_to_draft_then_commits_once() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    projector = NativeCodingEventProjector(app)

    projector.handle({"type": "message_start", "message": _assistant()})
    projector.handle(
        {
            "type": "message_update",
            "message": _assistant("你好"),
            "assistant_message_event": {"type": "text_delta", "delta": "你好"},
        }
    )

    assert app.state.assistant_draft == AssistantMessageRecord("你好", stable=False)
    assert not any(isinstance(record, AssistantMessageRecord) for record in app.state.records)

    projector.handle({"type": "message_end", "message": _assistant("你好，世界")})

    assert app.state.assistant_draft is None
    assert [record for record in app.state.records if isinstance(record, AssistantMessageRecord)] == [
        AssistantMessageRecord("你好，世界")
    ]


def test_native_event_projector_renders_user_message_and_skips_optimistic_echo() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    message = UserMessage(role="user", content=[TextPart(type="text", text="你好")], timestamp=0.0)
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)

    NativeCodingEventProjector(app).handle({"type": "message_start", "message": message})

    assert app.state.records == [UserPromptRecord("你好")]


def test_native_event_projector_skips_user_message_when_matching_pending_echo() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    message = UserMessage(role="user", content=[TextPart(type="text", text="你好")], timestamp=0.0)
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    app.start_prompt("你好", started_at=1.0)

    assert app.state.records == [UserPromptRecord("你好")]

    NativeCodingEventProjector(app).handle({"type": "message_start", "message": message})

    # Should not duplicate the user message because it matches the pending echo
    assert app.state.records == [UserPromptRecord("你好")]


def test_native_event_projector_drops_stale_pending_echo_on_mismatch() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    app.start_prompt("same", started_at=1.0)
    projector = NativeCodingEventProjector(app)

    projector.handle(
        {
            "type": "message_start",
            "message": UserMessage(role="user", content=[TextPart(type="text", text="different")], timestamp=0.0),
        }
    )
    projector.handle(
        {
            "type": "message_start",
            "message": UserMessage(role="user", content=[TextPart(type="text", text="same")], timestamp=0.0),
        }
    )

    assert app.state.records == [
        UserPromptRecord("same"),
        UserPromptRecord("different"),
        UserPromptRecord("same"),
    ]


def test_native_event_projector_updates_tool_record_in_place() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 5.0)
    projector = NativeCodingEventProjector(app, now=lambda: 5.0)
    result: AgentToolResult[dict[str, object]] = AgentToolResult(content=[TextPart(type="text", text="ok")], details={})

    projector.handle({"type": "tool_execution_start", "tool_call_id": "tc1", "tool_name": "read", "args": {"path": "README.md"}})
    assert len(app.state.records) == 1
    assert isinstance(app.state.records[0], ToolExecutionRecord)
    assert app.state.records[0].state == "running"

    projector.handle({"type": "tool_execution_end", "tool_call_id": "tc1", "tool_name": "read", "result": result, "is_error": False})

    assert len(app.state.records) == 1
    record = app.state.records[0]
    assert isinstance(record, ToolExecutionRecord)
    assert record.state == "completed"
    assert record.name == "read README.md"


def test_native_event_projector_syncs_pending_queues() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    projector = NativeCodingEventProjector(
        app,
        read_pending_steers=lambda: ("马上回答中文",),
        read_pending_followups=lambda: ("继续",),
    )

    projector.handle({"type": "queue_update"})

    assert app.state.pending_steers == ["马上回答中文"]
    assert app.state.pending_followups == ["继续"]


def test_native_event_projector_renders_queued_steer_into_transcript() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    app.start_prompt("初始问题", started_at=1.0)
    projector = NativeCodingEventProjector(app, read_pending_steers=tuple, read_pending_followups=tuple)
    projector.handle(
        {
            "type": "message_start",
            "message": UserMessage(role="user", content=[TextPart(type="text", text="初始问题")], timestamp=0.0),
        }
    )

    app.queue_steer("steer 消息")
    assert app.state.pending_steers == ["steer 消息"]
    projector.handle({"type": "queue_update"})
    assert app.state.pending_steers == []

    steer_message = UserMessage(role="user", content=[TextPart(type="text", text="steer 消息")], timestamp=0.0)
    projector.handle({"type": "message_start", "message": steer_message})

    user_records = [record for record in app.state.records if isinstance(record, UserPromptRecord)]
    assert len(user_records) == 2
    assert user_records[0].text == "初始问题"
    assert user_records[1].text == "steer 消息"


def test_native_event_projector_renders_queued_followup_into_transcript() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    app.start_prompt("初始问题", started_at=1.0)
    projector = NativeCodingEventProjector(app, read_pending_steers=tuple, read_pending_followups=tuple)
    projector.handle(
        {
            "type": "message_start",
            "message": UserMessage(role="user", content=[TextPart(type="text", text="初始问题")], timestamp=0.0),
        }
    )

    app.queue_followup("followup 消息")
    assert app.state.pending_followups == ["followup 消息"]
    projector.handle({"type": "queue_update"})
    assert app.state.pending_followups == []

    followup_message = UserMessage(role="user", content=[TextPart(type="text", text="followup 消息")], timestamp=0.0)
    projector.handle({"type": "message_start", "message": followup_message})

    user_records = [record for record in app.state.records if isinstance(record, UserPromptRecord)]
    assert len(user_records) == 2
    assert user_records[0].text == "初始问题"
    assert user_records[1].text == "followup 消息"


def test_native_event_projector_renders_same_text_queued_message_after_initial_echo() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    app.start_prompt("same", started_at=1.0)
    projector = NativeCodingEventProjector(app)

    message = UserMessage(role="user", content=[TextPart(type="text", text="same")], timestamp=0.0)
    projector.handle({"type": "message_start", "message": message})
    projector.handle({"type": "message_start", "message": message})

    assert app.state.records == [UserPromptRecord("same"), UserPromptRecord("same")]


def test_native_event_projector_appends_compaction_record_and_tracks_baseline_reset() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_events import NativeCodingEventProjector

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    app.state.records.extend(
        UserPromptRecord(f"old prompt {index}") if index % 2 == 0 else AssistantMessageRecord(f"old answer {index}")
        for index in range(120)
    )
    app.state.records.append(UserPromptRecord("recent prompt"))
    projector = NativeCodingEventProjector(app)

    projector.handle(
        {
            "type": "compaction_end",
            "result": {
                "summary": "condensed summary",
                "first_kept_entry_id": "entry-100",
                "tokens_before": 500_000,
            },
        }
    )

    assert app.state.evicted_prefix_record_count > 0
    assert isinstance(app.state.records[-1], ContextCompactionRecord)
    assert app.state.records[-1].summary == "condensed summary"
    assert app.state.records[-1].tokens_before == 500_000
    assert all(not getattr(record, "text", "").startswith("old prompt 0") for record in app.state.records)
    assert UserPromptRecord("recent prompt") in app.state.records
    assert app.consume_render_baseline_reset_reason() == "transcript_window_trimmed:context_compaction"
