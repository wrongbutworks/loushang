from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from loushang.ai import (
    AssistantMessage,
    Model,
    TextPart,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from loushang.coding.message import CompactionSummaryMessage
from loushang.coding.message.entries import SessionContext
from loushang.coding.types import ModelSelection
from loushang.coding.ui.native_surfaces import NativeSurfaceManager
from loushang.coding.ui.perf_probe import characterize_long_transcript_rendering
from loushang.observability import configure_debug_logging, reset_observability
from loushang.tui import RenderLoop, TerminalSize
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


class _TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


class _RecordingDebugSink:
    def __init__(self) -> None:
        self.events = []

    def write_log(self, **_kwargs) -> None:
        return None

    def write_problem(self, _record) -> None:
        return None

    def write_debug_event(self, record) -> None:
        self.events.append(record)


class _Session:
    def __init__(self) -> None:
        self.session_id = "254d6156"
        self.session_name = "254d6156"
        self.session_manager = SimpleNamespace(
            get_cwd=lambda: "/repo",
            get_session_file=lambda: Path("/tmp/254d6156.jsonl"),
        )
        self.current_model: object = ModelSelection(provider="unknown", model_id="unknown")
        self.model_details = [Model(id="kimi-for-coding", provider="moonshot", endpoint="kimi-code-anthropic")]
        self.prompts: list[str] = []
        self.listeners: list[Callable[[dict[str, object]], object]] = []
        self.unsubscribed = False
        self.steers: list[str] = []
        self.follow_ups: list[str] = []
        self.visible_steering: list[str] = []
        self.visible_follow_up: list[str] = []
        self.context_messages: list[object] = []

    def get_model_selection(self) -> object:
        return self.current_model

    def get_session_context(self) -> SessionContext:
        return SessionContext(messages=list(self.context_messages))

    def get_available_model_details(self) -> list[Model]:
        return self.model_details

    async def set_model(self, selection: object) -> None:
        if isinstance(selection, Model):
            self.current_model = ModelSelection(provider=selection.provider_id, model_id=selection.id)
        else:
            self.current_model = selection

    def subscribe(self, listener: Callable[[dict[str, object]], object]):
        self.listeners.append(listener)

        def unsubscribe() -> None:
            self.unsubscribed = True
            if listener in self.listeners:
                self.listeners.remove(listener)

        return unsubscribe

    async def prompt(self, text: str) -> None:
        self.prompts.append(text)
        await self._emit(
            {
                "type": "message_start",
                "message": UserMessage(role="user", content=[TextPart(type="text", text=text)], timestamp=0.0),
            }
        )
        await self._emit(
            {
                "type": "message_update",
                "message": SimpleNamespace(role="assistant"),
                "assistant_message_event": {"type": "text_delta", "content_index": 0, "delta": "hello back"},
            }
        )
        await self._emit(
            {"type": "message_end", "message": SimpleNamespace(role="assistant", content=[TextPart(type="text", text="hello back")])}
        )

    async def _emit(self, event: dict[str, object]) -> None:
        for listener in list(self.listeners):
            result = listener(event)
            if inspect.isawaitable(result):
                await result

    async def steer(self, text: str) -> None:
        self.steers.append(text)

    async def follow_up(self, text: str) -> None:
        self.follow_ups.append(text)

    def get_steering_messages(self) -> list[str]:
        return list(self.visible_steering)

    def get_follow_up_messages(self) -> list[str]:
        return list(self.visible_follow_up)

    def abort(self) -> None:
        return None

    def clear_queue(self) -> None:
        return None

    def abort_bash(self) -> None:
        return None


def test_run_coding_tui_interactive_uses_native_loop(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    captured: dict[str, object] = {}

    async def fake_native_loop(**kwargs):
        captured.update(kwargs)
        await kwargs["handle_prompt"]("hello")
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=_TTYStringIO(),
            stderr=StringIO(),
        )
    )

    native_app = captured["app"]
    records = getattr(native_app, "state").records
    assistant_records = [record for record in records if isinstance(record, AssistantMessageRecord)]
    assert exit_code == 0
    assert session.prompts == ["hello"]
    assert assistant_records[-1].text == "hello back"


def test_run_coding_tui_interactive_prints_resume_hint_on_clean_exit(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    stdout = _TTYStringIO()

    async def fake_native_loop(**kwargs):
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=stdout,
            stderr=StringIO(),
        )
    )

    assert exit_code == 0
    assert "Resume this session with:" in stdout.getvalue()
    assert "loushang --resume 254d6156" in stdout.getvalue()
    assert "loushang --tui --resume" not in stdout.getvalue()


def test_run_coding_tui_interactive_replays_resumed_session_history(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    usage = Usage(input=1, output=2, cache_read=0, cache_write=0, total_tokens=3, cost={})
    session.context_messages = [
        UserMessage(role="user", content=[TextPart(type="text", text="previous question")], timestamp=1.0),
        AssistantMessage(
            role="assistant",
            content=[TextPart(type="text", text="previous answer")],
            api="openai",
            provider="moonshot",
            model="kimi",
            response_id=None,
            usage=usage,
            stop_reason="stop",
            error_message=None,
            timestamp=2.0,
        ),
        ToolResultMessage(
            role="toolResult",
            tool_call_id="bash-1",
            tool_name="bash",
            content=[TextPart(type="text", text="file contents")],
            is_error=False,
            timestamp=3.0,
        ),
        CompactionSummaryMessage(role="compactionSummary", summary="older context summary", tokens_before=128, timestamp=4.0),
    ]
    captured: dict[str, object] = {}

    async def fake_native_loop(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=_TTYStringIO(),
            stderr=StringIO(),
        )
    )

    records = getattr(captured["app"], "state").records
    assert exit_code == 0
    assert isinstance(records[0], UserPromptRecord)
    assert records[0].text == "previous question"
    assert isinstance(records[1], AssistantMessageRecord)
    assert records[1].text == "previous answer"
    assert isinstance(records[2], ToolExecutionRecord)
    assert records[2].name.startswith("bash")
    assert records[2].output == "file contents"
    assert isinstance(records[3], ContextCompactionRecord)
    assert records[3].summary == "older context summary"
    assert records[3].tokens_before == 128


def test_run_coding_tui_interactive_bounds_resumed_long_transcript_render_window(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    usage = Usage(input=1, output=2, cache_read=0, cache_write=0, total_tokens=3, cost={})
    for turn in range(24):
        session.context_messages.append(
            UserMessage(role="user", content=[TextPart(type="text", text=f"question {turn}")], timestamp=float(turn))
        )
        line_count = 900 if turn == 23 else 40
        session.context_messages.append(
            AssistantMessage(
                role="assistant",
                content=[TextPart(type="text", text="\n".join(f"answer {turn} line {line}" for line in range(line_count)))],
                api="openai",
                provider="moonshot",
                model="kimi",
                response_id=None,
                usage=usage,
                stop_reason="stop",
                error_message=None,
                timestamp=float(turn) + 0.5,
            )
        )
    captured: dict[str, object] = {}

    async def fake_native_loop(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=_TTYStringIO(),
            stderr=StringIO(),
        )
    )

    app = captured["app"]
    render_loop = RenderLoop(screen_root=app)
    first_metrics = characterize_long_transcript_rendering(
        app,
        width=100,
        height=30,
        render_loop=render_loop,
        commit_plan=True,
    )
    input_metrics = characterize_long_transcript_rendering(
        app,
        width=100,
        height=30,
        composer_text="x",
        render_loop=render_loop,
        commit_plan=True,
    )

    assert exit_code == 0
    assert getattr(app, "state").evicted_prefix_record_count > 0
    assert first_metrics.render_loop_logical_line_count <= 380
    assert input_metrics.render_loop_logical_line_count <= 380
    assert input_metrics.render_loop_operation_class not in {
        "baseline_repaint",
        "managed_viewport_repaint",
        "recovery_repaint",
        "resize_repaint",
    }


def test_run_coding_tui_interactive_long_transcript_input_frame_does_not_clear_screen(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    usage = Usage(input=1, output=2, cache_read=0, cache_write=0, total_tokens=3, cost={})
    for turn in range(24):
        session.context_messages.append(
            UserMessage(role="user", content=[TextPart(type="text", text=f"question {turn}")], timestamp=float(turn))
        )
        session.context_messages.append(
            AssistantMessage(
                role="assistant",
                content=[TextPart(type="text", text="\n".join(f"answer {turn} line {line}" for line in range(80)))],
                api="openai",
                provider="moonshot",
                model="kimi",
                response_id=None,
                usage=usage,
                stop_reason="stop",
                error_message=None,
                timestamp=float(turn) + 0.5,
            )
        )
    captured: dict[str, object] = {}

    async def fake_native_loop(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=_TTYStringIO(),
            stderr=StringIO(),
        )
    )

    app = captured["app"]
    render_loop = RenderLoop(screen_root=app)
    size = TerminalSize(columns=100, rows=30)
    first = render_loop.plan(size)
    render_loop.commit(first, size=size)
    app.composer.set_text("x")
    second = render_loop.plan(size)

    assert exit_code == 0
    assert second.operation_class == "changed_range_update"
    assert {operation.kind for operation in second.operations}.isdisjoint({"clear_screen", "clear_scrollback"})


def test_run_coding_tui_interactive_long_transcript_working_timer_frame_stays_bounded(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    usage = Usage(input=1, output=2, cache_read=0, cache_write=0, total_tokens=3, cost={})
    for turn in range(24):
        session.context_messages.append(
            UserMessage(role="user", content=[TextPart(type="text", text=f"question {turn}")], timestamp=float(turn))
        )
        session.context_messages.append(
            AssistantMessage(
                role="assistant",
                content=[TextPart(type="text", text="\n".join(f"answer {turn} line {line}" for line in range(80)))],
                api="openai",
                provider="moonshot",
                model="kimi",
                response_id=None,
                usage=usage,
                stop_reason="stop",
                error_message=None,
                timestamp=float(turn) + 0.5,
            )
        )
    captured: dict[str, object] = {}

    async def fake_native_loop(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=_TTYStringIO(),
            stderr=StringIO(),
        )
    )

    app = captured["app"]
    app.now = lambda: 10.0
    app.begin_run(started_at=10.0)
    render_loop = RenderLoop(screen_root=app)
    size = TerminalSize(columns=100, rows=30)
    first = render_loop.plan(size)
    render_loop.commit(first, size=size)
    app.now = lambda: 10.2
    second = render_loop.plan(size)

    assert exit_code == 0
    assert len(second.current_logical_lines) <= 380
    assert second.operation_class == "changed_range_update"
    assert second.changed_line_range is not None
    assert second.changed_line_range[0] >= len(second.current_logical_lines) - 8
    assert {operation.kind for operation in second.operations}.isdisjoint({"clear_screen", "clear_scrollback"})


def test_run_coding_tui_interactive_traces_resumed_transcript_window_trim(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    usage = Usage(input=1, output=2, cache_read=0, cache_write=0, total_tokens=3, cost={})
    for turn in range(24):
        session.context_messages.append(
            UserMessage(role="user", content=[TextPart(type="text", text=f"question {turn}")], timestamp=float(turn))
        )
        session.context_messages.append(
            AssistantMessage(
                role="assistant",
                content=[TextPart(type="text", text="\n".join(f"answer {turn} line {line}" for line in range(80)))],
                api="openai",
                provider="moonshot",
                model="kimi",
                response_id=None,
                usage=usage,
                stop_reason="stop",
                error_message=None,
                timestamp=float(turn) + 0.5,
            )
        )
    sink = _RecordingDebugSink()
    captured: dict[str, object] = {}

    async def fake_native_loop(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)
    reset_observability()
    configure_debug_logging(debug_sink=sink, debug_scopes=("tui",))
    try:
        exit_code = asyncio.run(
            mode.run_coding_tui(
                runtime=object(),
                session=session,
                stdin=_TTYStringIO(),
                stdout=_TTYStringIO(),
                stderr=StringIO(),
            )
        )
    finally:
        reset_observability()

    event = next(event for event in sink.events if event.scope == "tui" and event.name == "tui.resume_history")
    app = captured["app"]
    assert exit_code == 0
    assert event.data["record_count"] == 48
    assert event.data["active_record_count"] == len(getattr(app, "state").records)
    assert event.data["evicted_record_count"] == getattr(app, "state").evicted_prefix_record_count
    assert event.data["trimmed"] is True


def test_run_coding_tui_interactive_native_loop_dispatches_steer_and_followup(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    captured: dict[str, object] = {}

    async def fake_native_loop(**kwargs):
        captured.update(kwargs)
        await kwargs["handle_steer"]("steer this")
        await kwargs["handle_followup"]("follow this")
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=_TTYStringIO(),
            stderr=StringIO(),
        )
    )

    assert exit_code == 0
    assert session.steers == ["steer this"]
    assert session.follow_ups == ["follow this"]


def test_run_coding_tui_injects_on_approval_callback(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    captured: dict[str, object] = {}

    class RecordingSurfaceManager(NativeSurfaceManager):
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["on_approval"] = kwargs.get("on_approval")
            super().__init__(*args, **kwargs)

    async def fake_native_loop(**kwargs: object) -> int:
        captured["loop_kwargs"] = kwargs
        return 0

    monkeypatch.setattr(mode, "NativeSurfaceManager", RecordingSurfaceManager)
    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=_TTYStringIO(),
            stderr=StringIO(),
        )
    )

    assert exit_code == 0
    on_approval = captured.get("on_approval")
    assert callable(on_approval)
    assert isinstance(captured.get("loop_kwargs"), dict)


def test_run_coding_tui_non_interactive_keeps_plain_prompt_loop(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    captured: dict[str, object] = {}

    async def fail_native_loop(**_kwargs):
        raise AssertionError("non-interactive mode should not enter native terminal loop")

    async def fake_prompt_loop(**kwargs):
        captured.update(kwargs)
        await kwargs["handle_prompt"]("hello")
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fail_native_loop)
    monkeypatch.setattr(mode, "run_non_interactive_prompt_loop", fake_prompt_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=StringIO("hello\n"),
            stdout=StringIO(),
            stderr=StringIO(),
        )
    )

    assert exit_code == 0
    assert session.prompts == ["hello"]
    assert set(captured) == {"stdin", "stdout", "handle_prompt"}


def test_native_event_projection_skips_duplicate_user_messages(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()

    async def prompt_with_user_event(text: str) -> None:
        session.prompts.append(text)
        await session._emit(
            {
                "type": "message_start",
                "message": type("Message", (), {"role": "user", "content": [TextPart(type="text", text=text)]})(),
            }
        )

    session.prompt = prompt_with_user_event  # type: ignore[method-assign]
    captured: dict[str, object] = {}

    async def fake_native_loop(**kwargs):
        captured.update(kwargs)
        app = kwargs["app"]
        app.start_prompt("hello")
        await kwargs["handle_prompt"]("hello")
        return 0

    monkeypatch.setattr(mode, "run_native_coding_tui", fake_native_loop)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=session,
            stdin=_TTYStringIO(),
            stdout=_TTYStringIO(),
            stderr=StringIO(),
        )
    )

    records = getattr(captured["app"], "state").records
    assert exit_code == 0
    assert [getattr(record, "text", None) for record in records] == ["hello"]
