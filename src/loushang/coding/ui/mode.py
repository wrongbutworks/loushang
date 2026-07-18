from __future__ import annotations

import inspect
import shlex
import time
import traceback
from collections.abc import Callable
from typing import Any, TextIO

from loushang.ai.types import ImagePart
from loushang.coding.observability import disable_session_debug, enable_session_debug
from loushang.coding.ui.completion import coding_inline_completion_provider
from loushang.coding.ui.controller import CodingUiController, ControllerResult
from loushang.coding.ui.intent import AbortIntent, QuitIntent, parse_prompt_intent
from loushang.coding.ui.plain_app import build_plain_coding_tui_app
from loushang.coding.ui.plain_events import PlainCodingEventRenderer
from loushang.coding.ui.plain_renderer import PlainCodingUiRenderer
from loushang.coding.ui.run_context import (
    open_coding_tui_run_context,
    subscribe_session_events,
)
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_events import ScreenCodingEventProjector
from loushang.coding.ui.screen_loop import run_screen_coding_tui
from loushang.coding.ui.screen_surfaces import ScreenSurfaceManager
from loushang.coding.ui.session_history import session_history_records
from loushang.coding.ui.session_view import is_running, session_label, thinking_level
from loushang.coding.ui.startup import (
    CodingTuiStartupSnapshot,
    load_coding_tui_startup_snapshot,
)
from loushang.coding.ui.status_provider import (
    CodingTuiStatusProvider,
    statusline_settings_from_settings_manager,
    statusline_settings_persistence_callback,
)
from loushang.coding.ui.transcript_source import SessionTranscriptSource
from loushang.observability import get_log, log_context
from loushang.tui import CompletionProvider
from loushang.tui.prompt import run_non_interactive_prompt_loop

log = get_log(__name__).bind(component="CodingUiMode")


async def run_coding_tui(
    *,
    runtime: Any,
    session: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    verbose: bool = False,
) -> int:
    interactive = _is_interactive(stdin=stdin, stdout=stdout)
    try:
        if interactive:
            return await _run_screen_interactive_tui(
                runtime=runtime,
                session=session,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                verbose=verbose,
            )
        return await _run_plain_tui(
            runtime=runtime,
            session=session,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            verbose=verbose,
        )
    except Exception as error:
        stdout.write(f"■ Error: {str(error) or error.__class__.__name__}\n")
        stdout.flush()
        if verbose:
            stderr.write(traceback.format_exc())
            stderr.flush()
        return 1


async def _run_screen_interactive_tui(
    *,
    runtime: Any,
    session: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    verbose: bool,
) -> int:
    snapshot = await load_coding_tui_startup_snapshot(runtime=runtime, session=session)
    app = ScreenCodingTuiApp(
        model_label=snapshot.model_label,
        cwd=snapshot.cwd,
        branch=snapshot.branch,
        session_label=snapshot.session_label,
        now=time.monotonic,
    )
    tool_definition_resolver = _tool_definition_resolver(session)
    app.transcript_source_factory = lambda: SessionTranscriptSource(
        session,
        tool_definition_resolver=tool_definition_resolver,
        active_window_state=app.state,
    )
    history_records = session_history_records(
        session, tool_definition_resolver=tool_definition_resolver
    )
    if history_records:
        app.replace_transcript_window(history_records, reason="resume")
        app.trim_active_transcript_window()
        _trace(
            "tui.resume_history",
            record_count=len(history_records),
            active_record_count=len(app.state.records),
            evicted_record_count=app.state.evicted_prefix_record_count,
            trimmed=app.state.evicted_prefix_record_count > 0,
        )
    completion_provider = await _load_completion_provider(session)
    app.composer.set_completion_provider(completion_provider)
    controller = CodingUiController(runtime=runtime, session=session, verbose=verbose)

    async def _handle_approval(event: dict[str, object]) -> bool:
        sink = getattr(session, "handle_screen_approval", None)
        if callable(sink):
            return bool(await _maybe_await(sink(event)))
        return False

    settings_manager = getattr(session, "settings_manager", None)
    status_provider = CodingTuiStatusProvider(
        model_label=snapshot.model_label,
        cwd=snapshot.cwd,
        branch=snapshot.branch,
        session_label=lambda: session_label(session),
        thinking_level=lambda: thinking_level(session),
        running=lambda: app.state.running or is_running(session),
        statusline_settings=statusline_settings_from_settings_manager(settings_manager),
        on_statusline_settings_changed=statusline_settings_persistence_callback(
            settings_manager
        ),
    )
    app.set_statusline_settings(status_provider.statusline_settings())
    surface_manager = ScreenSurfaceManager(
        app=app,
        session=session,
        status_provider=status_provider,
        on_approval=_handle_approval,
    )
    unbind_approval_presenter = _bind_screen_approval_presenter(
        session,
        surface_manager,
        session_provider=lambda: _runtime_session(runtime, session),
    )

    def unbind_session_transition() -> None:
        return None

    def unsubscribe() -> None:
        return None

    try:
        unbind_session_transition = _bind_screen_session_transition(
            runtime,
            surface_manager,
        )
        projector = ScreenCodingEventProjector(
            app,
            tool_definition_resolver=_tool_definition_resolver(session),
            read_pending_steers=_queue_reader(session, "get_steering_messages"),
            read_pending_followups=_queue_reader(session, "get_follow_up_messages"),
            now=time.monotonic,
        )
        with log_context(
            session_id=snapshot.session_observability_id,
            cwd=snapshot.cwd,
            mode="tui",
        ):
            try:
                _trace_start(snapshot, interactive=True)
                unsubscribe = subscribe_session_events(session, projector.handle)
                exit_code = await run_screen_coding_tui(
                    app=app,
                    stdin=stdin,
                    stdout=stdout,
                    handle_prompt=_screen_prompt_handler(
                        app=app,
                        controller=controller,
                        stderr=stderr,
                        verbose=verbose,
                    ),
                    handle_local=surface_manager.handle_text,
                    handle_steer=_screen_text_handler(
                        app=app,
                        dispatch=controller.steer,
                        label="Steering failed",
                    ),
                    handle_followup=_screen_text_handler(
                        app=app,
                        dispatch=controller.follow_up,
                        label="Follow-up failed",
                    ),
                    handle_surface_intent=surface_manager.handle_surface_intent,
                    on_abort=_screen_abort_handler(controller),
                    should_exit=_screen_should_exit,
                    is_local_command=surface_manager.is_local_command,
                    keybindings=_session_keybindings(session),
                )
                _write_resume_hint_for_clean_exit(
                    session=session,
                    stdout=stdout,
                    exit_code=exit_code,
                )
                return exit_code
            finally:
                try:
                    _trace("tui.end")
                finally:
                    unsubscribe()
    finally:
        try:
            unbind_session_transition()
        finally:
            try:
                surface_manager.clear_approval_surfaces()
            finally:
                unbind_approval_presenter()


def _bind_screen_approval_presenter(
    session: Any,
    surface_manager: ScreenSurfaceManager,
    *,
    session_provider: Callable[[], Any] | None = None,
) -> Callable[[], None]:
    setter = getattr(session, "set_approval_presenter", None)
    if not callable(setter):
        return lambda: None

    def present(payload: dict[str, object]) -> None:
        action = payload.get("action")
        risk = payload.get("risk")
        action_id = payload.get("action_id")
        surface_manager.open_approval(
            action=action if isinstance(action, str) else "Approve tool call",
            risk=risk if isinstance(risk, str) else "",
            action_id=action_id if isinstance(action_id, str) else None,
        )

    setter(present, dismisser=surface_manager.dismiss_approval)

    def unbind() -> None:
        target = session_provider() if session_provider is not None else session
        _unbind_session_approval_presenter(target)
        if target is not session:
            _unbind_session_approval_presenter(session)

    return unbind


def _unbind_session_approval_presenter(session: Any) -> None:
    host_unbind = getattr(session, "_unbind_approval_presenter_host", None)
    if callable(host_unbind):
        host_unbind()
        return
    setter = getattr(session, "set_approval_presenter", None)
    if callable(setter):
        setter(None)


def _runtime_session(runtime: Any, fallback: Any) -> Any:
    getter = getattr(runtime, "get_current_session", None)
    if callable(getter):
        current = getter()
        if current is not None:
            return current
    current = getattr(runtime, "current_session", None)
    return current if current is not None else fallback


def _bind_screen_session_transition(
    runtime: Any,
    surface_manager: ScreenSurfaceManager,
) -> Callable[[], None]:
    subscribe = getattr(runtime, "subscribe_after_session_invalidate", None)
    if not callable(subscribe):
        subscribe = getattr(runtime, "subscribe_before_session_invalidate", None)
    if not callable(subscribe):
        return lambda: None
    unsubscribe = subscribe(surface_manager.clear_approval_surfaces)
    return unsubscribe if callable(unsubscribe) else lambda: None


async def _run_plain_tui(
    *,
    runtime: Any,
    session: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    verbose: bool,
) -> int:
    renderer = PlainCodingUiRenderer(stdout=stdout, stderr=stderr, verbose=verbose)
    run_context = None
    try:
        snapshot = await load_coding_tui_startup_snapshot(
            runtime=runtime, session=session
        )
        event_renderer = PlainCodingEventRenderer(
            renderer, tool_definition_resolver=_tool_definition_resolver(session)
        )
        run_context = open_coding_tui_run_context(
            session=session,
            snapshot=snapshot,
            event_renderer=event_renderer,
            interactive=False,
            log_context_factory=log_context,
            trace=_trace,
        )
        app = build_plain_coding_tui_app(
            runtime=runtime,
            session=session,
            renderer=renderer,
            event_renderer=event_renderer,
            stderr=stderr,
            verbose=verbose,
            model_label=snapshot.model_label,
            cwd=snapshot.cwd,
            branch=snapshot.branch,
            emit=run_context.emit,
            trace=_trace,
            now=time.monotonic,
            enable_debug=enable_session_debug,
            disable_debug=disable_session_debug,
        )
        renderer.render_header(
            project_label=snapshot.project_label,
            cwd=snapshot.cwd,
            branch=snapshot.branch,
            session_label=snapshot.session_label,
            model_label=snapshot.model_label,
        )
        return await run_non_interactive_prompt_loop(
            stdin=stdin, stdout=stdout, handle_prompt=app.handlers.handle_prompt
        )
    finally:
        if run_context is not None:
            run_context.close()


def _screen_prompt_handler(
    *,
    app: ScreenCodingTuiApp,
    controller: CodingUiController,
    stderr: TextIO,
    verbose: bool,
):
    async def handle(
        text: str, *, images: tuple[ImagePart, ...] | None = None
    ) -> int | None:
        intent = parse_prompt_intent(text)
        if intent is None:
            return None
        if isinstance(intent, QuitIntent):
            return 0
        if images is not None and hasattr(intent, "images"):
            intent = type(intent)(intent.text, images=images)
        result = await controller.dispatch(intent)
        _record_controller_result(
            app=app, result=result, stderr=stderr, verbose=verbose
        )
        return result.exit_code

    return handle


def _screen_text_handler(
    *,
    app: ScreenCodingTuiApp,
    dispatch: Any,
    label: str,
):
    async def handle(
        text: str, *, images: tuple[ImagePart, ...] | None = None
    ) -> int | None:
        if images is not None and _supports_keyword(dispatch, "images"):
            result = await _maybe_await(dispatch(text, images=images))
        else:
            result = await _maybe_await(dispatch(text))
        if isinstance(result, ControllerResult):
            _record_controller_result(
                app=app, result=result, stderr=None, verbose=False, status_label=label
            )
            return result.exit_code
        return result if isinstance(result, int) else None

    return handle


def _screen_abort_handler(controller: CodingUiController):
    async def handle() -> None:
        await controller.dispatch(AbortIntent())
        await controller.wait_for_idle()

    return handle


def _record_controller_result(
    *,
    app: ScreenCodingTuiApp,
    result: ControllerResult,
    stderr: TextIO | None,
    verbose: bool,
    status_label: str = "Request failed",
) -> None:
    if result.error_message:
        app.add_error(result.error_message)
        app.set_status(f"{status_label}: {result.error_message}")
    elif result.status_message:
        app.add_status(result.status_message)
        app.set_status(result.status_message)
    if verbose and stderr is not None and result.traceback_text:
        stderr.write(result.traceback_text)
        stderr.flush()


def _screen_should_exit(text: str) -> bool:
    return isinstance(parse_prompt_intent(text), QuitIntent)


def _write_resume_hint_for_clean_exit(
    *, session: Any, stdout: TextIO, exit_code: int
) -> None:
    if exit_code != 0:
        return
    command = _resume_command_for_session(session)
    if command is None:
        return
    stdout.write(f"\nResume this session with:\n{command}\n")
    stdout.flush()


def _resume_command_for_session(session: Any) -> str | None:
    resume_ref = _resume_ref_for_session(session)
    if resume_ref is None:
        return None
    return " ".join(shlex.quote(part) for part in ("loushang", "--resume", resume_ref))


def _resume_ref_for_session(session: Any) -> str | None:
    session_file = _session_file_for_resume(session)
    if session_file is None:
        return None

    session_id = getattr(session, "session_id", None)
    if isinstance(session_id, str) and session_id:
        return session_id

    manager = getattr(session, "session_manager", None)
    get_header = getattr(manager, "get_header", None)
    if callable(get_header):
        try:
            header = get_header()
        except Exception:
            header = None
        header_id = getattr(header, "conversation_id", None)
        if isinstance(header_id, str) and header_id:
            return header_id

    return str(session_file)


def _session_file_for_resume(session: Any) -> object | None:
    manager = getattr(session, "session_manager", None)
    get_session_file = getattr(manager, "get_session_file", None)
    if callable(get_session_file):
        try:
            return get_session_file()
        except Exception:
            return None
    return getattr(session, "session_file", None)


def _session_keybindings(session: Any) -> object | None:
    settings_manager = getattr(session, "settings_manager", None)
    if settings_manager is None:
        return None
    get_keybindings = getattr(settings_manager, "get_keybindings", None)
    if callable(get_keybindings):
        return get_keybindings()
    get_settings = getattr(settings_manager, "get_settings", None)
    if callable(get_settings):
        return getattr(get_settings(), "keybindings", None)
    return None


def _trace_start(snapshot: CodingTuiStartupSnapshot, *, interactive: bool) -> None:
    _trace(
        "tui.start",
        interactive=interactive,
        model=snapshot.model_label,
        cwd=snapshot.cwd,
        branch=snapshot.branch,
        session=snapshot.session_label,
    )


def _trace(name: str, **data: Any) -> None:
    log.debug_event("tui", name, **data)


def _is_interactive(*, stdin: TextIO, stdout: TextIO) -> bool:
    stdin_is_tty = getattr(stdin, "isatty", lambda: False)
    stdout_is_tty = getattr(stdout, "isatty", lambda: False)
    return bool(stdin_is_tty() and stdout_is_tty())


async def _load_completion_provider(session: Any) -> CompletionProvider:
    try:
        return await coding_inline_completion_provider(session)
    except Exception as error:
        log.problem(
            "coding_ui_completion_provider_failed",
            source="tui",
            message=str(error) or error.__class__.__name__,
            recoverable=True,
            exc=error,
        )
        return CompletionProvider(())


def _tool_definition_resolver(session: Any):
    getter = getattr(session, "getToolDefinition", None)
    if not callable(getter):
        getter = getattr(session, "get_tool_definition", None)
    return getter if callable(getter) else None


def _queue_reader(session: Any, method_name: str):
    def read() -> tuple[str, ...]:
        method = getattr(session, method_name, None)
        if not callable(method):
            return ()
        try:
            values = method()
        except Exception:
            return ()
        if not isinstance(values, list | tuple):
            return ()
        return tuple(value for value in values if isinstance(value, str))

    return read


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
