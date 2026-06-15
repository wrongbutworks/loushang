from __future__ import annotations

import asyncio
import inspect
import shutil
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from typing import Any, TextIO

from loushang.ai.types import ImagePart
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import ScreenInputRouter
from loushang.tui import _runner_utils
from loushang.tui.core import RenderConstraints
from loushang.tui.input import InputIntent, InputReader
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager
from loushang.tui.render_loop import RenderLoop
from loushang.tui.runtime import TuiRuntime
from loushang.tui.scheduler import RenderRequestKind
from loushang.tui.terminal import ProcessTerminalPort, TerminalSize
from loushang.tui.terminal_capabilities import format_terminal_capability_diagnostics
from loushang.tui.terminal_input import (
    read_input_chunk_or_render_tick,
)
from loushang.tui.terminal_session import TerminalSession

PromptHandler = Callable[..., Awaitable[int | None] | int | None]
TextHandler = Callable[..., Awaitable[int | None] | int | None]
SurfaceIntentHandler = Callable[[InputIntent], Awaitable[int | None] | int | None]
AbortHandler = Callable[[], Awaitable[object] | object]
ShouldExit = Callable[[str], bool]
LocalCommandPredicate = Callable[[str], bool]
TerminalModeFactory = Callable[[TextIO, TextIO], AbstractContextManager[object]]
TerminalSizeProvider = Callable[[], TerminalSize]

_finish_tui_exit = _runner_utils.finish_tui_exit
_flush_pending_input = _runner_utils.flush_pending_input
_input_events_for_chunk = _runner_utils.input_events_for_chunk
_poll_terminal_runtime = _runner_utils.poll_terminal_runtime
_request_runtime_render = _runner_utils.request_runtime_render
_terminal_runtime_wakeup_ms = _runner_utils.terminal_runtime_wakeup_ms


async def run_screen_coding_tui(
    *,
    app: ScreenCodingTuiApp,
    stdin: TextIO,
    stdout: TextIO,
    handle_prompt: PromptHandler,
    handle_local: TextHandler | None = None,
    handle_steer: TextHandler | None = None,
    handle_followup: TextHandler | None = None,
    handle_surface_intent: SurfaceIntentHandler | None = None,
    on_abort: AbortHandler,
    should_exit: ShouldExit,
    is_local_command: LocalCommandPredicate | None = None,
    keybindings: KeybindingManager | KeybindingConfig | None = None,
    terminal_mode_factory: TerminalModeFactory | None = None,
    terminal_size_provider: TerminalSizeProvider | None = None,
) -> int:
    reader = InputReader()
    size_provider = terminal_size_provider or _terminal_size
    initial_size = size_provider()
    router = ScreenInputRouter(
        app,
        should_exit=should_exit,
        is_local_command=is_local_command or (lambda _text: False),
        keybindings=keybindings,
        width=initial_size.columns,
        height=initial_size.rows,
    )
    runtime = TuiRuntime(
        render_loop=RenderLoop(app),
        terminal=ProcessTerminalPort(output=stdout, size_provider=size_provider, track_screen=False),
    )
    app.surface_host = runtime.overlay_host()
    mode_factory = terminal_mode_factory or (lambda input_stream, output_stream: TerminalSession(stdin=input_stream, stdout=output_stream))
    active_task: asyncio.Task[int | None] | None = None
    active_prompt_started_at: float | None = None
    queued_steers_while_running: list[str] = []
    render_wakeup = asyncio.Event()
    previous_render_requester = app.render_requester
    previous_terminal_diagnostics_provider = app.terminal_diagnostics_provider
    previous_terminal_capabilities = app.terminal_capabilities

    def request_app_render(kind: RenderRequestKind) -> None:
        if previous_render_requester is not None:
            previous_render_requester(kind)
        runtime.request_render(kind)
        render_wakeup.set()

    app.render_requester = request_app_render
    try:
        with mode_factory(stdin, stdout) as terminal_context:
            app.terminal_diagnostics_provider = lambda context=terminal_context: _format_terminal_diagnostics(context)
            _configure_runtime_for_terminal_context(runtime, app, terminal_context)
            _write_startup_welcome(app=app, runtime=runtime, stdout=stdout)
            runtime.render_now()
            while True:
                if active_task is not None and active_task.done():
                    exit_code = await _finish_active_task(
                        app=app,
                        active_task=active_task,
                        started_at=active_prompt_started_at,
                    )
                    active_task = None
                    active_prompt_started_at = None
                    queued_steers_while_running = []
                    runtime.render_now()
                    if exit_code is not None:
                        return _finish_tui_exit(runtime=runtime, stdout=stdout, exit_code=exit_code)

                data = await read_input_chunk_or_render_tick(
                    stdin,
                    runtime=runtime,
                    active_task=active_task,
                    render_wakeup=render_wakeup,
                    pending_input_idle_ms=10 if reader.has_pending else None,
                    idle_wakeup_ms=_terminal_runtime_wakeup_ms(terminal_context),
                )
                input_events: tuple[Any, ...]
                if data is None:
                    _poll_terminal_runtime(terminal_context)
                    if not reader.has_pending:
                        continue
                    input_events = _flush_pending_input(reader, terminal_context=terminal_context)
                elif data == "" and reader.has_pending:
                    input_events = _flush_pending_input(reader, terminal_context=terminal_context)
                elif data == "":
                    if active_task is not None:
                        exit_code = await _finish_active_task(
                            app=app,
                            active_task=active_task,
                            started_at=active_prompt_started_at,
                        )
                        runtime.render_now()
                        return _finish_tui_exit(runtime=runtime, stdout=stdout, exit_code=exit_code if exit_code is not None else 0)
                    runtime.render_now()
                    return _finish_tui_exit(runtime=runtime, stdout=stdout, exit_code=0)
                else:
                    input_events = _input_events_for_chunk(reader, data, terminal_context=terminal_context)

                for event in input_events:
                    result = router.handle(event)
                    if result.exit_code is not None:
                        runtime.render_now()
                        return _finish_tui_exit(runtime=runtime, stdout=stdout, exit_code=result.exit_code)
                    if result.abort_requested:
                        queued_steers_while_running = []
                        interrupt_pending_steer = _pop_interrupt_pending_steer(app)
                        await _abort_active(app=app, active_task=active_task, on_abort=on_abort)
                        active_task = None
                        active_prompt_started_at = None
                        runtime.render_now()
                        if interrupt_pending_steer is not None:
                            app.start_pending_prompt(interrupt_pending_steer)
                            active_task = asyncio.create_task(_run_prompt_handler(handle_prompt, interrupt_pending_steer))
                            active_prompt_started_at = app.state.active_started_at
                            runtime.render_now()
                        continue
                    if result.prompt_text is not None:
                        active_prompt_started_at = app.state.active_started_at
                        active_task = asyncio.create_task(
                            _run_prompt_handler(handle_prompt, result.prompt_text, images=result.prompt_images)
                        )
                        queued_steers_while_running = []
                    if result.local_text is not None and handle_local is not None:
                        exit_code = await _run_text_handler(handle_local, result.local_text)
                        if exit_code is not None:
                            runtime.render_now()
                            return _finish_tui_exit(runtime=runtime, stdout=stdout, exit_code=exit_code)
                    if result.steer_text is not None and handle_steer is not None:
                        was_running = active_task is not None
                        exit_code = await _run_text_handler(handle_steer, result.steer_text, images=result.steer_images)
                        if was_running:
                            queued_steers_while_running.append(result.steer_text)
                        if exit_code is not None:
                            runtime.render_now()
                            return _finish_tui_exit(runtime=runtime, stdout=stdout, exit_code=exit_code)
                    if result.followup_text is not None and handle_followup is not None:
                        exit_code = await _run_text_handler(handle_followup, result.followup_text, images=result.followup_images)
                        if exit_code is not None:
                            runtime.render_now()
                            return _finish_tui_exit(runtime=runtime, stdout=stdout, exit_code=exit_code)
                    if result.surface_intent is not None and handle_surface_intent is not None:
                        exit_code = await _run_surface_intent_handler(handle_surface_intent, result.surface_intent)
                        if exit_code is not None:
                            runtime.render_now()
                            return _finish_tui_exit(runtime=runtime, stdout=stdout, exit_code=exit_code)
                    if result.render_requested:
                        _request_runtime_render(runtime, "input")
    finally:
        app.surface_host = None
        app.terminal_diagnostics_provider = previous_terminal_diagnostics_provider
        app.terminal_capabilities = previous_terminal_capabilities
        app.render_requester = previous_render_requester


async def _finish_active_task(
    *,
    app: ScreenCodingTuiApp,
    active_task: asyncio.Task[int | None],
    started_at: float | None,
) -> int | None:
    try:
        result = await active_task
    except asyncio.CancelledError:
        app.state.abort(message="Operation aborted", elapsed_seconds=app.elapsed_seconds())
        return None
    except Exception as error:  # noqa: BLE001
        app.add_error(str(error) or error.__class__.__name__)
        app.complete_run(elapsed_seconds=_elapsed_since(app, started_at))
        return 1
    app.complete_run(elapsed_seconds=_elapsed_since(app, started_at))
    return result if isinstance(result, int) else None


def _write_startup_welcome(*, app: ScreenCodingTuiApp, runtime: TuiRuntime, stdout: TextIO) -> None:
    if app.state.records or app.state.running or app.state.assistant_draft_buffer is not None:
        return
    size = runtime.terminal.size()
    result = app.startup_welcome_panel().render(
        RenderConstraints(width=size.columns, max_height=size.rows, visible_height=size.rows)
    )
    if not result.lines:
        return
    stdout.write("\n".join(line.text for line in result.lines))
    stdout.write("\n\n")
    stdout.flush()


def _configure_runtime_for_terminal_context(runtime: TuiRuntime, app: ScreenCodingTuiApp, terminal_context: object) -> None:
    capabilities = getattr(terminal_context, "capabilities", None)
    if capabilities is not None:
        app.terminal_capabilities = capabilities
    _runner_utils.configure_runtime_for_terminal_context(runtime, terminal_context)


def _format_terminal_diagnostics(terminal_context: object) -> str:
    sections: list[str] = []
    environment = getattr(terminal_context, "environment", None)
    capabilities = getattr(terminal_context, "capabilities", None)
    if environment is not None or capabilities is not None:
        sections.append(format_terminal_capability_diagnostics(environment, capabilities))
    diagnostics_getter = getattr(terminal_context, "diagnostics", None)
    if callable(diagnostics_getter):
        diagnostics = diagnostics_getter()
        sections.append(
            "\n".join(
                (
                    f"keyboard_protocol_state: {_diagnostic_value(diagnostics, 'keyboard_protocol_state')}",
                    f"mouse_mode_active: {_format_bool(_diagnostic_value(diagnostics, 'mouse_mode_active'))}",
                    f"cell_size: {_format_cell_size(_diagnostic_value(diagnostics, 'cell_size'))}",
                    f"runtime_image_protocol: {_diagnostic_value(diagnostics, 'image_protocol')}",
                    f"alternate_screen_active: {_format_bool(_diagnostic_value(diagnostics, 'alternate_screen'))}",
                    f"tmux_passthrough_active: {_format_bool(_diagnostic_value(diagnostics, 'tmux_passthrough'))}",
                    f"windows_vt_input_active: {_format_bool(_diagnostic_value(diagnostics, 'windows_vt_input'))}",
                    f"windows_vt_output_active: {_format_bool(_diagnostic_value(diagnostics, 'windows_vt_output'))}",
                    f"windows_console_mode_active: {_format_bool(_diagnostic_value(diagnostics, 'windows_console_mode_active'))}",
                    f"windows_output_mode_active: {_format_bool(_diagnostic_value(diagnostics, 'windows_output_mode_active'))}",
                    f"termux_session_active: {_format_bool(_diagnostic_value(diagnostics, 'termux_session'))}",
                    f"multiplexer_active: {_format_bool(_diagnostic_value(diagnostics, 'is_multiplexer'))}",
                    f"ssh_active: {_format_bool(_diagnostic_value(diagnostics, 'inside_ssh'))}",
                )
            )
        )
    return "\n\n".join(section for section in sections if section) or "Terminal diagnostics are unavailable."


def _diagnostic_value(diagnostics: object, name: str) -> object:
    return getattr(diagnostics, name, "<unknown>")


def _format_bool(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_cell_size(value: object) -> str:
    width = getattr(value, "width_px", None)
    height = getattr(value, "height_px", None)
    if isinstance(width, int) and isinstance(height, int):
        return f"{width}x{height}"
    return "<unknown>"


async def _abort_active(
    *,
    app: ScreenCodingTuiApp,
    active_task: asyncio.Task[int | None] | None,
    on_abort: AbortHandler,
) -> None:
    await _maybe_await(on_abort())
    if active_task is not None and not active_task.done():
        active_task.cancel()
        try:
            await active_task
        except asyncio.CancelledError:
            pass
    elif active_task is not None:
        await active_task
    app.state.abort(message="Conversation interrupted - tell the model what to do differently.", elapsed_seconds=app.elapsed_seconds())


def _elapsed_since(app: ScreenCodingTuiApp, started_at: float | None) -> float:
    if started_at is None:
        return app.elapsed_seconds()
    return max(0.0, app.now() - started_at)


async def _run_prompt_handler(
    handler: PromptHandler,
    text: str,
    *,
    images: tuple[ImagePart, ...] | None = None,
) -> int | None:
    result = await _call_text_handler(handler, text, images=images)
    return result if isinstance(result, int) else None


async def _run_text_handler(
    handler: TextHandler,
    text: str,
    *,
    images: tuple[ImagePart, ...] | None = None,
) -> int | None:
    result = await _call_text_handler(handler, text, images=images)
    return result if isinstance(result, int) else None


def _pop_interrupt_pending_steer(app: ScreenCodingTuiApp) -> str | None:
    if not app.state.pending_steers:
        return None
    pending_steer = app.state.pending_steers.pop(0)
    return pending_steer


async def _call_text_handler(
    handler: Callable[..., object],
    text: str,
    *,
    images: tuple[ImagePart, ...] | None = None,
) -> object:
    if images is not None and _supports_keyword(handler, "images"):
        return await _maybe_await(handler(text, images=images))
    return await _maybe_await(handler(text))


async def _run_surface_intent_handler(handler: SurfaceIntentHandler, intent: InputIntent) -> int | None:
    result = await _maybe_await(handler(intent))
    return result if isinstance(result, int) else None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _supports_keyword(method: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD or parameter.name == keyword
        for parameter in signature.parameters.values()
    )


def _terminal_size() -> TerminalSize:
    size = shutil.get_terminal_size((80, 24))
    return TerminalSize(columns=size.columns, rows=size.lines)


__all__ = ["run_screen_coding_tui"]
