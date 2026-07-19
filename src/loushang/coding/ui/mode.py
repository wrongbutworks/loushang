from __future__ import annotations

import time
from functools import partial
from typing import Any, TextIO

from loushang.coding.event.presentation_policy import event_writes_transcript
from loushang.coding.interaction.controller import CodingUiController
from loushang.coding.interaction.intent import QuitIntent, parse_prompt_intent
from loushang.coding.interaction.screen_host import (
    ScreenCodingConversationActionHost,
)
from loushang.coding.observability import disable_session_debug, enable_session_debug
from loushang.coding.policy.tui import (
    bind_screen_approval_presenter,
    bind_screen_session_transition,
    handle_screen_approval,
    runtime_session,
)
from loushang.coding.presentation.resume import write_resume_hint_for_clean_exit
from loushang.coding.presentation.session import (
    is_running,
    session_label,
    thinking_level,
)
from loushang.coding.presentation.tui.history import (
    SessionTranscriptSource,
    session_history_records,
)
from loushang.coding.presentation.tui.plain import (
    PlainCodingEventRenderer,
    PlainCodingUiRenderer,
)
from loushang.coding.presentation.tui.runtime import (
    pending_followups_reader,
    pending_steers_reader,
    session_keybindings,
    tool_definition_resolver,
)
from loushang.coding.presentation.tui.screen import ScreenCodingEventProjector
from loushang.coding.ui.completion import coding_inline_completion_provider
from loushang.coding.ui.plain_app import build_plain_coding_tui_app
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import CODING_SCREEN_RUN_PROFILE
from loushang.coding.ui.screen_surfaces import ScreenSurfaceManager
from loushang.coding.ui.startup import (
    CodingTuiStartupSnapshot,
    load_coding_tui_startup_snapshot,
)
from loushang.harnesstui.conversation.dispatch import StableEventStreamHandler
from loushang.harnesstui.conversation.host import (
    run_action_host_conversation_screen,
)
from loushang.harnesstui.conversation.run_context import (
    open_interaction_run_context,
    subscribe_events,
)
from loushang.harnesstui.status.persistence import (
    statusline_settings_from_store,
    statusline_settings_persistence_callback,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.observability import get_log, log_context
from loushang.tui import CompletionProvider
from loushang.tui.launch import TuiLaunchProfile, run_tui_launch_shell
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
    return await run_tui_launch_shell(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        profile=TuiLaunchProfile(
            run_screen=partial(
                _run_screen_interactive_tui,
                runtime=runtime,
                session=session,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                verbose=verbose,
            ),
            run_plain=partial(
                _run_plain_tui,
                runtime=runtime,
                session=session,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                verbose=verbose,
            ),
            error_prefix="■ Error: ",
        ),
        verbose=verbose,
    )


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
    tool_resolver = tool_definition_resolver(session)
    app.transcript_source_factory = lambda: SessionTranscriptSource(
        session,
        tool_definition_resolver=tool_resolver,
        active_window_state=app.state,
    )
    history_records = session_history_records(
        session,
        tool_definition_resolver=tool_resolver,
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
    action_host = ScreenCodingConversationActionHost(
        presenter=app,
        controller=controller,
        stderr=stderr,
        verbose=verbose,
    )

    settings_manager = getattr(session, "settings_manager", None)
    status_provider = StatusProvider(
        model_label=snapshot.model_label,
        cwd=snapshot.cwd,
        branch=snapshot.branch,
        session_label=lambda: session_label(session),
        thinking_level=lambda: thinking_level(session),
        running=lambda: app.state.running or is_running(session),
        statusline_settings=statusline_settings_from_store(settings_manager),
        on_statusline_settings_changed=statusline_settings_persistence_callback(
            settings_manager
        ),
    )
    app.set_statusline_settings(status_provider.statusline_settings())
    surface_manager = ScreenSurfaceManager(
        app=app,
        session=session,
        status_provider=status_provider,
        on_approval=lambda event: handle_screen_approval(session, event),
    )
    unbind_approval_presenter = bind_screen_approval_presenter(
        session,
        surface_manager,
        session_provider=lambda: runtime_session(runtime, session),
    )

    def unbind_session_transition() -> None:
        return None

    def unsubscribe() -> None:
        return None

    try:
        unbind_session_transition = bind_screen_session_transition(
            runtime,
            surface_manager,
        )
        projector = ScreenCodingEventProjector(
            app,
            tool_definition_resolver=tool_resolver,
            read_pending_steers=pending_steers_reader(session),
            read_pending_followups=pending_followups_reader(session),
            now=time.monotonic,
        )
        with log_context(
            session_id=snapshot.session_observability_id,
            cwd=snapshot.cwd,
            mode="tui",
        ):
            try:
                _trace_start(snapshot, interactive=True)
                unsubscribe = subscribe_events(session, projector.handle)
                exit_code = await run_action_host_conversation_screen(
                    app=app,
                    stdin=stdin,
                    stdout=stdout,
                    action_host=action_host,
                    profile=CODING_SCREEN_RUN_PROFILE,
                    handle_local=surface_manager.handle_text,
                    handle_surface_intent=surface_manager.handle_surface_intent,
                    should_exit=_screen_should_exit,
                    is_local_command=surface_manager.is_local_command,
                    keybindings=session_keybindings(session),
                )
                write_resume_hint_for_clean_exit(
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
            renderer,
            tool_definition_resolver=tool_definition_resolver(session),
        )
        run_context = open_interaction_run_context(
            event_source=session,
            listener=event_renderer.handle,
            interactive_listener_factory=lambda emit: (
                StableEventStreamHandler(
                    renderer=event_renderer,
                    emit=emit,
                    writes_stably=event_writes_transcript,
                    event_type=lambda event: str(event.get("type") or "unknown"),
                    trace=_trace,
                ).handle
            ),
            exit_context=log_context(
                session_id=snapshot.session_observability_id,
                cwd=snapshot.cwd,
                mode="tui",
            ),
            interactive=False,
            trace=_trace,
            on_open=lambda: _trace_start(snapshot, interactive=False),
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
            stdin=stdin,
            stdout=stdout,
            handle_prompt=app.handle_prompt,
        )
    finally:
        if run_context is not None:
            run_context.close()


def _screen_should_exit(text: str) -> bool:
    return isinstance(parse_prompt_intent(text), QuitIntent)


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
