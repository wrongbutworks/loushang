from __future__ import annotations

import asyncio
from io import StringIO
from types import SimpleNamespace

from loushang.ai import Model
from loushang.coding.types import ModelSelection


class _TTYStringIO(StringIO):
    def isatty(self) -> bool:
        return True


class _Session:
    def __init__(self) -> None:
        self.session_id = "254d6156"
        self.session_name = "254d6156"
        self.session_manager = SimpleNamespace(get_cwd=lambda: "/repo")
        self.current_model: object = ModelSelection(provider="unknown", model_id="unknown")
        self.model_details = [Model(id="kimi-for-coding", provider="moonshot", endpoint="kimi-code-anthropic")]
        self.set_model_calls: list[object] = []
        self.prompts: list[str] = []
        self.listeners: list[object] = []
        self.unsubscribed = False

    def get_model_selection(self) -> object:
        return self.current_model

    def get_available_model_details(self) -> list[Model]:
        return self.model_details

    def get_available_models(self) -> list[ModelSelection]:
        return [
            ModelSelection(provider="moonshot", model_id="kimi-for-coding"),
            ModelSelection(provider="openai", model_id="gpt-5.4"),
        ]

    async def set_model(self, selection: object) -> None:
        self.set_model_calls.append(selection)
        if isinstance(selection, Model):
            self.current_model = ModelSelection(provider=selection.provider_id, model_id=selection.id)
        else:
            self.current_model = selection

    def subscribe(self, listener):
        self.listeners.append(listener)

        def unsubscribe() -> None:
            self.unsubscribed = True
            if listener in self.listeners:
                self.listeners.remove(listener)

        return unsubscribe

    async def prompt(self, text: str) -> None:
        self.prompts.append(text)

    def clear_queue(self) -> None:
        return None

    def abort_bash(self) -> None:
        return None


def test_run_coding_tui_uses_screen_loop_for_interactive_terminal(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    captured: dict[str, object] = {}

    async def fake_screen_loop(**kwargs):
        captured.update(kwargs)
        return 0

    async def fail_prompt_loop(**_kwargs):
        raise AssertionError("interactive mode should not use non-interactive prompt loop")

    monkeypatch.setattr(mode, "run_screen_coding_tui", fake_screen_loop)
    monkeypatch.setattr(mode, "run_non_interactive_prompt_loop", fail_prompt_loop)

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
    assert captured["app"].__class__.__name__ == "ScreenCodingTuiApp"
    assert (
        captured["action_host"].__class__.__name__
        == "ScreenCodingConversationActionHost"
    )
    assert callable(captured["handle_local"])
    assert callable(captured["handle_surface_intent"])


def test_run_coding_tui_non_interactive_keeps_plain_prompt_loop(monkeypatch) -> None:
    from loushang.coding.ui import mode

    session = _Session()
    captured: dict[str, object] = {}

    async def fail_screen_loop(**_kwargs):
        raise AssertionError("non-interactive mode should not enter screen terminal loop")

    async def fake_prompt_loop(**kwargs):
        captured.update(kwargs)
        await kwargs["handle_prompt"]("hello")
        return 0

    monkeypatch.setattr(mode, "run_screen_coding_tui", fail_screen_loop)
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


def test_run_coding_tui_handles_startup_error(monkeypatch) -> None:
    from loushang.coding.ui import mode

    async def fail_startup(**_kwargs):
        raise RuntimeError("startup exploded")

    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.setattr(mode, "load_coding_tui_startup_snapshot", fail_startup)

    exit_code = asyncio.run(
        mode.run_coding_tui(
            runtime=object(),
            session=_Session(),
            stdin=_TTYStringIO(),
            stdout=stdout,
            stderr=stderr,
        )
    )

    assert exit_code == 1
    assert "■ Error: startup exploded" in stdout.getvalue()
    assert stderr.getvalue() == ""
