from __future__ import annotations

import asyncio


def test_build_plain_coding_tui_app_wires_prompt_handler_without_legacy_status_api() -> (
    None
):
    from loushang.coding.ui.plain_app import build_plain_coding_tui_app
    from loushang.harnesstui.conversation.control import ConversationTextAction
    from loushang.tui import CompletionItem, CompletionProvider

    emitted: list[str] = []
    traces: list[str] = []
    enabled_debug: list[tuple[object, tuple[str, ...]]] = []
    completion_provider = CompletionProvider((CompletionItem(value="/terminal"),))

    class Session:
        session_id = "sid"
        session_name = "session-name"

        def __init__(self) -> None:
            self.prompts: list[str] = []
            self.follow_ups: list[str] = []

        async def prompt(self, text: str) -> None:
            self.prompts.append(text)
            if text == "cancel":
                app.lifecycle.mark_abort_requested()
                raise asyncio.CancelledError

        async def follow_up(self, text: str) -> None:
            self.follow_ups.append(text)

        def get_thinking_level(self) -> str:
            return "high"

    class Renderer:
        def render_status(self, text: str) -> None:
            emitted.append(f"status:{text}")

        def render_error(self, text: str) -> None:
            emitted.append(f"error:{text}")

        def render_worked(self, elapsed_seconds: float) -> None:
            emitted.append(f"worked:{elapsed_seconds:.1f}")

    class EventRenderer:
        last_error_message = None

    async def emit(write, *, label: str):
        emitted.append(label)
        write()

    session = Session()
    app = build_plain_coding_tui_app(
        runtime=None,
        session=session,
        renderer=Renderer(),
        event_renderer=EventRenderer(),
        stderr=_Writer(),
        verbose=False,
        model_label="moonshot/kimi",
        cwd="/repo",
        branch="main",
        emit=emit,
        trace=lambda name, **_data: traces.append(name),
        now=lambda: 10.0,
        enable_debug=lambda *, session, scopes: (
            enabled_debug.append((session, scopes)) or "/tmp/debug.log"
        ),
        disable_debug=lambda: None,
        completion_provider=completion_provider,
    )

    result = asyncio.run(app.handle_prompt("hello"))
    cancelled = asyncio.run(app.handle_prompt("cancel"))
    app.lifecycle.begin_work()
    queued = asyncio.run(app.action_host.follow_up(ConversationTextAction("  next  ")))

    assert result is None
    assert cancelled is None
    assert queued is None
    assert session.prompts == ["hello", "cancel"]
    assert session.follow_ups == ["next"]
    assert "worked:0.0" in emitted
    assert "status:Follow-up queued." in emitted
    assert "error:Request cancelled." not in emitted
    assert "prompt.suppressed_cancelled" in traces
    assert app.lifecycle.aborted_id is None
    assert not hasattr(app, "status")
    assert not hasattr(app, "status_visible")
    assert "prompt.dispatch.start" in traces
    assert enabled_debug == []
    assert app.completion_provider is completion_provider


def test_build_plain_coding_tui_app_wires_model_palette_chooser() -> None:
    from loushang.coding.types import ModelSelection
    from loushang.coding.ui.plain_app import build_plain_coding_tui_app
    from loushang.tui import CommandPalette

    emitted: list[str] = []
    seen: list[CommandPalette] = []

    class Session:
        session_id = "sid"
        session_name = "session-name"

        def __init__(self) -> None:
            self.selection = ModelSelection(
                provider="moonshot", model_id="kimi-for-coding"
            )
            self.set_model_calls: list[ModelSelection] = []

        def get_model_selection(self) -> ModelSelection:
            return self.selection

        def get_available_models(self) -> list[ModelSelection]:
            return [
                ModelSelection(provider="moonshot", model_id="kimi-for-coding"),
                ModelSelection(provider="openai", model_id="gpt-5.4"),
            ]

        async def set_model(self, selection: ModelSelection) -> None:
            self.set_model_calls.append(selection)
            self.selection = selection

    class Renderer:
        def render_status(self, text: str) -> None:
            emitted.append(f"status:{text}")

        def render_error(self, text: str) -> None:
            emitted.append(f"error:{text}")

        def render_worked(self, elapsed_seconds: float) -> None:
            emitted.append(f"worked:{elapsed_seconds:.1f}")

    class EventRenderer:
        last_error_message = None

    async def emit(write, *, label: str):
        emitted.append(label)
        write()

    async def choose(palette: CommandPalette) -> str:
        seen.append(palette)
        return "openai/gpt-5.4"

    session = Session()
    app = build_plain_coding_tui_app(
        runtime=None,
        session=session,
        renderer=Renderer(),
        event_renderer=EventRenderer(),
        stderr=_Writer(),
        verbose=False,
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        emit=emit,
        trace=lambda _name, **_data: None,
        now=lambda: 10.0,
        enable_debug=lambda *, session, scopes: "/tmp/debug.log",
        disable_debug=lambda: None,
        model_palette_chooser=choose,
    )

    result = asyncio.run(app.handle_prompt("/model"))

    assert result is None
    assert emitted == ["model:select", "status:Model set: openai/gpt-5.4"]
    assert session.set_model_calls == [
        ModelSelection(provider="openai", model_id="gpt-5.4")
    ]
    assert seen


def test_build_plain_coding_tui_app_wires_command_palette_chooser() -> None:
    from types import SimpleNamespace

    from loushang.coding.ui.plain_app import build_plain_coding_tui_app
    from loushang.tui import CommandPalette

    emitted: list[str] = []
    seen: list[CommandPalette] = []

    class Session:
        session_id = "sid"
        session_name = "session-name"

        def list_commands(self) -> list[object]:
            return [SimpleNamespace(name="demo", description="Demo command")]

    class Renderer:
        def render_status(self, text: str) -> None:
            emitted.append(f"status:{text}")

        def render_error(self, text: str) -> None:
            emitted.append(f"error:{text}")

        def render_worked(self, elapsed_seconds: float) -> None:
            emitted.append(f"worked:{elapsed_seconds:.1f}")

    class EventRenderer:
        last_error_message = None

    async def emit(write, *, label: str):
        emitted.append(label)
        write()

    async def choose(palette: CommandPalette) -> str:
        seen.append(palette)
        return "/demo"

    app = build_plain_coding_tui_app(
        runtime=None,
        session=Session(),
        renderer=Renderer(),
        event_renderer=EventRenderer(),
        stderr=_Writer(),
        verbose=False,
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        emit=emit,
        trace=lambda _name, **_data: None,
        now=lambda: 10.0,
        enable_debug=lambda *, session, scopes: "/tmp/debug.log",
        disable_debug=lambda: None,
        command_palette_chooser=choose,
    )

    result = asyncio.run(app.handle_prompt("/command"))

    assert result is None
    assert emitted == ["command:select", "status:Command selected: /demo"]
    assert seen and seen[0].title == "Commands"


def test_build_plain_coding_tui_app_renders_plain_settings_summary() -> None:
    from loushang.coding.ui.plain_app import build_plain_coding_tui_app

    emitted: list[str] = []

    class Session:
        session_id = "sid"
        session_name = "session-name"

        def get_thinking_level(self) -> str:
            return "high"

    class Renderer:
        def render_status(self, text: str) -> None:
            emitted.append(f"status:{text}")

        def render_error(self, text: str) -> None:
            emitted.append(f"error:{text}")

        def render_worked(self, elapsed_seconds: float) -> None:
            emitted.append(f"worked:{elapsed_seconds:.1f}")

    class EventRenderer:
        last_error_message = None

    async def emit(write, *, label: str):
        emitted.append(label)
        write()

    app = build_plain_coding_tui_app(
        runtime=None,
        session=Session(),
        renderer=Renderer(),
        event_renderer=EventRenderer(),
        stderr=_Writer(),
        verbose=False,
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        emit=emit,
        trace=lambda _name, **_data: None,
        now=lambda: 10.0,
        enable_debug=lambda *, session, scopes: "/tmp/debug.log",
        disable_debug=lambda: None,
    )

    result = asyncio.run(app.handle_prompt("/settings"))

    assert result is None
    assert emitted == ["settings:show", "status:Settings\nStatus line: true"]
    assert not hasattr(app, "status_visible")


def test_build_plain_coding_tui_app_wires_info_panel_presenter() -> None:
    from loushang.coding.ui.plain_app import build_plain_coding_tui_app
    from loushang.tui import InfoPanel

    emitted: list[str] = []
    seen: list[InfoPanel] = []

    class Session:
        session_id = "sid"
        session_name = "session-name"

        def get_thinking_level(self) -> str:
            return "high"

    class Renderer:
        def render_status(self, text: str) -> None:
            emitted.append(f"status:{text}")

        def render_error(self, text: str) -> None:
            emitted.append(f"error:{text}")

        def render_worked(self, elapsed_seconds: float) -> None:
            emitted.append(f"worked:{elapsed_seconds:.1f}")

    class EventRenderer:
        last_error_message = None

    async def emit(write, *, label: str):
        emitted.append(label)
        write()

    async def present(panel: InfoPanel) -> bool:
        seen.append(panel)
        return True

    app = build_plain_coding_tui_app(
        runtime=None,
        session=Session(),
        renderer=Renderer(),
        event_renderer=EventRenderer(),
        stderr=_Writer(),
        verbose=False,
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        emit=emit,
        trace=lambda _name, **_data: None,
        now=lambda: 10.0,
        enable_debug=lambda *, session, scopes: "/tmp/debug.log",
        disable_debug=lambda: None,
        info_panel_presenter=present,
    )

    result = asyncio.run(app.handle_prompt("/hotkeys"))

    assert result is None
    assert emitted == []
    assert seen and seen[0].title == "Hotkeys"
    assert "Running Enter: steer current run" in seen[0].lines


class _Writer:
    def __init__(self) -> None:
        self.text = ""

    def write(self, text: str) -> None:
        self.text += text

    def flush(self) -> None:
        pass
