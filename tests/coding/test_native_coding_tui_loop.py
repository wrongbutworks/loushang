from __future__ import annotations

import asyncio
import time
from io import StringIO
from types import SimpleNamespace

from loushang.ai.types import ImagePart
from loushang.coding.types import ModelSelection
from loushang.tui import strip_control_sequences


def test_native_loop_prints_welcome_panel_to_scrollback_once() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    app = NativeCodingTuiApp(
        model_label="moonshot/kimi-for-coding",
        cwd="/home/dev/workspace/loushang",
        branch="main",
        session_label="9d591443",
        now=lambda: 1.0,
    )

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("/quit\r"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
        )
    )

    rendered = strip_control_sequences(stdout.getvalue())

    assert result == 0
    assert rendered.count("Welcome to Loushang CLI") == 1
    assert "欲穷千里目，更上一层楼" in rendered
    assert "From Loushang's height, farther horizons unfold." in rendered
    assert "Directory: /home/dev/workspace/loushang" in rendered
    assert rendered.find("Welcome to Loushang CLI") < rendered.rfind("› ")


def test_native_loop_runs_prompt_to_worked_divider_without_stale_working() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=_Clock([10.0, 10.5, 11.0]))

    async def handle_prompt(text: str) -> int | None:
        app.begin_assistant()
        app.append_assistant_chunk(f"收到：{text}")
        app.end_assistant()
        return None

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("你好\r"),
            stdout=stdout,
            handle_prompt=handle_prompt,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
        )
    )

    rendered = strip_control_sequences(stdout.getvalue())
    assert result == 0
    assert "› 你好" in rendered
    assert "• 收到：你好" in rendered
    assert "Worked for" in rendered
    assert rendered.rfind("Working") < rendered.rfind("Worked for")


def test_native_loop_passes_prompt_images_to_handler() -> None:
    from loushang.coding.ui.native_loop import _run_prompt_handler

    seen: dict[str, object] = {}
    image = ImagePart(type="image", data="abc", mime_type="image/png")

    async def handle_prompt(text: str, *, images: tuple[ImagePart, ...] | None = None) -> int | None:
        seen["text"] = text
        seen["images"] = images
        return 7

    result = asyncio.run(_run_prompt_handler(handle_prompt, "describe", images=(image,)))

    assert result == 7
    assert seen == {"text": "describe", "images": (image,)}


def test_native_loop_scripted_prompt_then_quit_exits_without_status_residue() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    app = NativeCodingTuiApp(
        model_label="kimi",
        cwd="/repo",
        branch="main",
        session_label="abcd",
        now=_Clock([10.0, 10.2, 10.4]),
    )

    async def handle_prompt(text: str) -> int | None:
        app.begin_assistant()
        app.append_assistant_chunk(f"收到：{text}")
        app.end_assistant()
        return None

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("你好\r/quit\r"),
            stdout=stdout,
            handle_prompt=handle_prompt,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
        )
    )

    raw_output = stdout.getvalue()
    rendered = strip_control_sequences(raw_output)
    final_cleanup = "\r\x1b[2K\n"

    assert result == 0
    assert "› 你好" in rendered
    assert "• 收到：你好" in rendered
    assert "Worked for" in rendered
    assert not raw_output.endswith(final_cleanup)
    _assert_exit_cleanup_clears_bottom_frame(raw_output)


def test_native_loop_exits_on_quit_command() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("/quit\r"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
        )
    )

    assert result == 0
    assert app.state.records == []
    _assert_exit_cleanup_clears_bottom_frame(stdout.getvalue())


def test_native_loop_clears_completion_area_before_exit() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("/quit\r"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
            is_local_command=lambda text: text.startswith("/"),
        )
    )

    rendered = strip_control_sequences(stdout.getvalue())

    assert result == 0
    assert "Commands" not in rendered
    assert "->" not in rendered
    _assert_exit_cleanup_clears_bottom_frame(stdout.getvalue())


def test_native_loop_escape_cancels_standalone_completion_chunk() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui
    from loushang.tui import CompletionItem, CompletionProvider

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    app.composer.set_completion_provider(
        CompletionProvider(
            (
                CompletionItem(value="/help", label="/help", description="Show help"),
                CompletionItem(value="/quit", label="/quit", description="Quit"),
            )
        )
    )

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("/\x1b"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
            is_local_command=lambda text: text.startswith("/"),
        )
    )

    rendered = strip_control_sequences(stdout.getvalue())

    assert result == 0
    assert app.composer.value == "/"
    assert not app.composer.has_completions
    assert "kimi | repo | main | abcd | idle" in rendered[rendered.rfind("› /") :]


def test_native_loop_enter_executes_selected_slash_completion() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui
    from loushang.tui import CompletionItem, CompletionProvider

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    app.composer.set_completion_provider(
        CompletionProvider(
            (
                CompletionItem(value="/quit", label="/quit", description="Quit"),
                CompletionItem(value="/help", label="/help", description="Show help"),
            )
        )
    )
    checked_exits: list[str] = []

    def should_exit(text: str) -> bool:
        checked_exits.append(text)
        return text in {"/quit", "/exit"}

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("/q\r"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            on_abort=lambda: None,
            should_exit=should_exit,
            is_local_command=lambda text: text.startswith("/"),
        )
    )

    assert result == 0
    assert checked_exits[-1] == "/quit"
    assert app.composer.value == ""


def test_native_loop_routes_runtime_overlay_surface_input() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui
    from loushang.coding.ui.native_surfaces import NativeSurfaceView
    from loushang.tui import CommandSurface, InputIntent, SelectItem, Surface

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    surface_intents: list[InputIntent] = []

    def handle_local(text: str) -> None:
        assert text == "/surface"
        assert app.surface_host is not None
        view = NativeSurfaceView(
            title="Commands",
            purpose="command",
            content=CommandSurface([SelectItem("/model", value="/model")]),
        )
        app.surface_host.open_surface(Surface(renderable=view, focus_target=view))

    def handle_surface_intent(intent: InputIntent) -> None:
        surface_intents.append(intent)

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("/surface\r\r"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            handle_local=handle_local,
            handle_surface_intent=handle_surface_intent,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
            is_local_command=lambda text: text == "/surface",
        )
    )

    assert result == 0
    assert surface_intents == [InputIntent(kind="command", text="/model")]
    assert app.surface_host is None


def test_native_loop_escape_closes_model_surface_and_restores_prompt() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui
    from loushang.coding.ui.native_surfaces import NativeSurfaceManager
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="moonshot/kimi-for-coding", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    session = _ModelSurfaceSession()
    manager = NativeSurfaceManager(
        app=app,
        session=session,
        status_provider=CodingTuiStatusProvider(
            model_label=app.state.model_label,
            cwd=app.state.cwd,
            branch=app.state.branch,
            session_label=lambda: app.state.session_label,
            thinking_level=lambda: None,
            running=lambda: app.state.running,
        ),
    )

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=_BlockingAfterScriptInput("/model\r\x1b"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            handle_local=manager.handle_text,
            handle_surface_intent=manager.handle_surface_intent,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
            is_local_command=manager.is_local_command,
        )
    )

    rendered = strip_control_sequences(stdout.getvalue())

    assert result == 0
    assert app.surface_host is None
    assert app.active_surface is None
    assert rendered.rfind("moonshot/kimi-for-coding | repo | main | abcd | idle") > rendered.rfind("Select Model")


def test_native_loop_exposes_terminal_diagnostics_provider_while_running() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui
    from loushang.tui import TerminalRuntimeCapabilities

    class _Mode:
        capabilities = TerminalRuntimeCapabilities(image_protocol="kitty", truecolor=True)

        def __enter__(self) -> "_Mode":
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def diagnostics(self) -> object:
            return SimpleNamespace(
                keyboard_protocol_state="kitty",
                mouse_mode_active=True,
                cell_size=SimpleNamespace(width_px=9, height_px=18),
                image_protocol="kitty",
                alternate_screen=False,
                tmux_passthrough=True,
                windows_vt_input=False,
                termux_session=False,
                is_multiplexer=False,
                inside_ssh=False,
            )

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 1.0)
    diagnostics_text: list[str] = []
    runtime_capabilities: list[TerminalRuntimeCapabilities | None] = []

    def handle_local(text: str) -> None:
        assert text == "/probe"
        assert app.terminal_diagnostics_provider is not None
        diagnostics_text.append(app.terminal_diagnostics_provider())
        runtime_capabilities.append(app.terminal_capabilities)

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("/probe\r"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            handle_local=handle_local,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
            is_local_command=lambda text: text == "/probe",
            terminal_mode_factory=lambda _stdin, _stdout: _Mode(),
        )
    )

    assert result == 0
    assert app.terminal_diagnostics_provider is None
    assert app.terminal_capabilities is None
    assert diagnostics_text
    assert runtime_capabilities == [_Mode.capabilities]
    assert "keyboard_protocol_state: kitty" in diagnostics_text[-1]
    assert "mouse_mode_active: true" in diagnostics_text[-1]
    assert "cell_size: 9x18" in diagnostics_text[-1]
    assert "alternate_screen_active: false" in diagnostics_text[-1]
    assert "tmux_passthrough_active: true" in diagnostics_text[-1]


def test_native_loop_normalizes_terminal_input_before_reader_parses_events() -> None:
    from loushang.coding.ui.native_loop import _input_events_for_chunk
    from loushang.tui.input import InputReader

    class _Context:
        def normalize_input_chunk(self, data: str) -> str:
            return "\x1b[13;2u" if data == "\r" else data

    events = _input_events_for_chunk(InputReader(), "\r", terminal_context=_Context())

    assert len(events) == 1
    assert events[0].kind == "key"
    assert events[0].key == "shift+enter"


def test_native_loop_dispatches_steer_and_followup_handlers() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=_Clock([10.0, 10.5]))
    steers: list[str] = []
    followups: list[str] = []

    async def handle_prompt(_text: str) -> int | None:
        app.begin_assistant()
        app.append_assistant_chunk("still running")
        await asyncio.Event().wait()
        return None

    async def handle_steer(text: str) -> int | None:
        steers.append(text)
        return None

    async def handle_followup(text: str) -> int | None:
        followups.append(text)
        return None

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("start\rsteer\rfollow\x1b\r\x03"),
            stdout=stdout,
            handle_prompt=handle_prompt,
            handle_steer=handle_steer,
            handle_followup=handle_followup,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
        )
    )

    assert result == 0
    assert steers == ["steer"]
    assert followups == ["follow"]


def test_native_loop_dispatches_pending_steer_from_escape_when_idle() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 10.0)
    app.state.pending_steers.append("你好")
    steers: list[str] = []

    async def handle_steer(text: str) -> int | None:
        steers.append(text)
        return None

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=StringIO("\x1b"),
            stdout=stdout,
            handle_prompt=lambda _text: None,
            handle_steer=handle_steer,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
        )
    )

    assert result == 0
    assert steers == ["你好"]


def test_native_loop_renders_streaming_updates_without_waiting_for_keyboard() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    stdin = _BlockingAfterScriptInput("go\r")
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd")

    async def handle_prompt(_text: str) -> int | None:
        app.begin_assistant()
        app.append_assistant_chunk("first chunk")
        await asyncio.sleep(0.12)
        app.append_assistant_chunk(" second chunk")
        return None

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=stdin,
            stdout=stdout,
            handle_prompt=handle_prompt,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
        )
    )

    rendered = strip_control_sequences(stdout.getvalue())
    assert result == 0
    assert rendered.count("first chunk") >= 2
    assert "first chunk second chunk" in rendered


def test_native_loop_wakes_stream_render_before_active_interval() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_loop import run_native_coding_tui

    stdout = StringIO()
    stdin = _BlockingAfterScriptInput("go\r")
    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd")

    async def handle_prompt(_text: str) -> int | None:
        app.begin_assistant()
        app.append_assistant_chunk("first chunk")
        await asyncio.sleep(0.03)
        app.append_assistant_chunk(" second chunk")
        return None

    result = asyncio.run(
        run_native_coding_tui(
            app=app,
            stdin=stdin,
            stdout=stdout,
            handle_prompt=handle_prompt,
            on_abort=lambda: None,
            should_exit=lambda text: text in {"/quit", "/exit"},
        )
    )

    rendered = strip_control_sequences(stdout.getvalue())
    assert result == 0
    assert rendered.count("first chunk") >= 2
    assert "first chunk second chunk" in rendered


class _Clock:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def __call__(self) -> float:
        if len(self._values) == 1:
            return self._values[0]
        return self._values.pop(0)


class _ModelSurfaceSession:
    def __init__(self) -> None:
        self.current_model = ModelSelection(provider="moonshot", model_id="kimi-for-coding")
        self.models = [
            ModelSelection(provider="moonshot", model_id="kimi-for-coding"),
            ModelSelection(provider="openai", model_id="gpt-5.4"),
        ]

    def get_model_selection(self) -> ModelSelection:
        return self.current_model

    def get_available_models(self) -> list[ModelSelection]:
        return self.models

    def get_available_model_details(self) -> list[object]:
        return []


def _assert_exit_cleanup_clears_bottom_frame(raw_output: str) -> None:
    cleanup_start = raw_output.rfind("\x1b[?25l\x1b[?2026h\r\x1b[2K")
    assert cleanup_start >= 0
    cleanup = raw_output[cleanup_start:]
    rendered_cleanup = strip_control_sequences(cleanup)
    assert "kimi | repo | main | abcd | idle" not in rendered_cleanup
    assert "moonshot/kimi-for-coding" not in rendered_cleanup
    assert "\x1b[2A\r" in cleanup
    assert cleanup.endswith("\x1b[?2026l\x1b[?25h")


class _BlockingAfterScriptInput:
    def __init__(self, script: str, *, block_seconds: float = 0.15) -> None:
        self._script = list(script)
        self._block_seconds = block_seconds

    def read(self, _size: int) -> str:
        if self._script:
            return self._script.pop(0)
        time.sleep(self._block_seconds)
        return ""

    def isatty(self) -> bool:
        return False
