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
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    ToolExecutionRecord,
    UserPromptRecord,
)


class _TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


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
    assert "loushang --tui --resume 254d6156" in stdout.getvalue()


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
