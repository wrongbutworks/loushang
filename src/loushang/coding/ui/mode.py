from __future__ import annotations

import time
from functools import partial
from pathlib import Path
from typing import Any, Protocol, TextIO, cast

from loushang.coding.policy.tui import (
    bind_screen_approval_presenter,
    bind_screen_session_transition,
    handle_screen_approval,
    runtime_session,
)
from loushang.coding.presentation.resume import coding_resume_hint_for_session
from loushang.coding.presentation.tui.history import (
    session_history_records,
)
from loushang.coding.presentation.tui.plain import (
    PlainCodingUiRenderer,
)
from loushang.coding.ui.completion import coding_inline_completion_provider
from loushang.coding.ui.plain_app import build_plain_coding_tui_app
from loushang.coding.ui.product_binding import (
    build_coding_ui_controller,
    build_screen_coding_action_host,
)
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import CODING_SCREEN_RUN_PROFILE
from loushang.coding.ui.screen_surfaces import ScreenSurfaceManager
from loushang.coding.ui.startup import load_coding_tui_startup_view
from loushang.harness.diagnostics import observability_runtime
from loushang.harness.presentation import RenderableToolDefinition
from loushang.harnesstui.conversation.agent_binding import (
    build_agent_plain_conversation_projection,
    build_agent_screen_conversation_projection,
)
from loushang.harnesstui.conversation.application_host import (
    InstalledConversationHistory,
    PreparedPlainConversationRun,
    PreparedScreenConversationRun,
    run_prepared_plain_conversation,
    run_prepared_screen_conversation,
)
from loushang.harnesstui.conversation.host import (
    run_action_host_conversation_screen,
)
from loushang.harnesstui.conversation.intents import (
    QuitIntent,
    parse_conversation_intent,
)
from loushang.harnesstui.conversation.resume import write_clean_exit_resume_hint
from loushang.harnesstui.conversation.run_context import StableEmit
from loushang.harnesstui.conversation.runtime_view import stable_string_queue_reader
from loushang.harnesstui.conversation.session_view import (
    is_running,
    session_label,
    thinking_level,
)
from loushang.harnesstui.conversation.source import MaterializedTranscriptSource
from loushang.harnesstui.conversation.startup import ConversationStartupView
from loushang.harnesstui.status.persistence import (
    statusline_settings_from_store,
    statusline_settings_persistence_callback,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.observability import get_log, log_context
from loushang.tui import CompletionProvider
from loushang.tui.launch import TuiLaunchProfile, run_tui_launch_shell
from loushang.tui.prompt import run_non_interactive_prompt_loop
from loushang.tui.transcript import DisplayRecord

log = get_log(__name__).bind(component="CodingUiMode")


class _CodingTuiSessionPort(Protocol):
    @property
    def session_manager(self) -> Any: ...

    @property
    def settings_manager(self) -> Any | None: ...

    def get_tool_definition(self, name: str) -> RenderableToolDefinition | None: ...
    def get_steering_messages(self) -> object: ...
    def get_follow_up_messages(self) -> object: ...


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
    session_port = cast(_CodingTuiSessionPort, session)
    snapshot = await load_coding_tui_startup_view(runtime=runtime, session=session)
    app = ScreenCodingTuiApp(
        model_label=snapshot.model_label,
        cwd=snapshot.cwd,
        branch=snapshot.branch,
        session_label=snapshot.session_label,
        now=time.monotonic,
    )
    tool_resolver = session_port.get_tool_definition

    def materialize_history() -> tuple[DisplayRecord, ...]:
        return session_history_records(
            session_port.session_manager.get_branch(),
            tool_definition_resolver=tool_resolver,
        )

    history_records = materialize_history()
    completion_provider = await _load_completion_provider(
        session, base_path=Path(snapshot.cwd)
    )
    controller = build_coding_ui_controller(
        runtime=runtime,
        session=session,
        verbose=verbose,
    )
    action_host = build_screen_coding_action_host(
        presenter=app,
        controller=controller,
        stderr=stderr,
        verbose=verbose,
    )

    settings_manager = session_port.settings_manager
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
    prepared = PreparedScreenConversationRun(
        app=app,
        action_host=action_host,
        surface=surface_manager,
        event_source=session,
        event_listener_factory=lambda: (
            build_agent_screen_conversation_projection(
                app,
                tool_definition_resolver=tool_resolver,
                read_pending_steers=stable_string_queue_reader(
                    session_port.get_steering_messages
                ),
                read_pending_followups=stable_string_queue_reader(
                    session_port.get_follow_up_messages
                ),
                now=time.monotonic,
            ).handle
        ),
        interaction_context=log_context(
            session_id=snapshot.session_observability_id,
            cwd=snapshot.cwd,
            mode="tui",
        ),
        profile=CODING_SCREEN_RUN_PROFILE,
        should_exit=_screen_should_exit,
        trace=_trace,
        keybindings=(
            settings_manager.get_keybindings()
            if settings_manager is not None
            else None
        ),
        history_records=history_records,
        transcript_source_factory=lambda: MaterializedTranscriptSource(
            materialize_records=materialize_history,
            active_window_state=app.state,
        ),
        completion_provider=completion_provider,
        bind_presenter=lambda: bind_screen_approval_presenter(
            session,
            surface_manager,
            session_provider=lambda: runtime_session(runtime, session),
        ),
        bind_transition=lambda: bind_screen_session_transition(
            runtime,
            surface_manager,
        ),
        on_history_installed=_trace_resume_history,
        on_start=lambda: _trace_start(snapshot, interactive=True),
        on_clean_exit=lambda exit_code: write_clean_exit_resume_hint(
            stdout=stdout,
            exit_code=exit_code,
            hint=coding_resume_hint_for_session(session),
        ),
    )
    return await run_prepared_screen_conversation(
        prepared,
        stdin=stdin,
        stdout=stdout,
        screen_runner=run_action_host_conversation_screen,
    )


async def _run_plain_tui(
    *,
    runtime: Any,
    session: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    verbose: bool,
) -> int:
    session_port = cast(_CodingTuiSessionPort, session)
    renderer = PlainCodingUiRenderer(stdout=stdout, stderr=stderr, verbose=verbose)
    snapshot = await load_coding_tui_startup_view(runtime=runtime, session=session)
    event_renderer = build_agent_plain_conversation_projection(
        renderer,
        tool_definition_resolver=session_port.get_tool_definition,
    )

    def build_app(emit: StableEmit):
        return build_plain_coding_tui_app(
            runtime=runtime,
            session=session,
            renderer=renderer,
            event_renderer=event_renderer,
            stderr=stderr,
            verbose=verbose,
            cwd=snapshot.cwd,
            emit=emit,
            trace=_trace,
            now=time.monotonic,
            enable_debug=observability_runtime.enable_session_debug,
            disable_debug=observability_runtime.disable_session_debug,
        )

    prepared = PreparedPlainConversationRun(
        event_source=session,
        event_listener=event_renderer.handle,
        interaction_context=log_context(
            session_id=snapshot.session_observability_id,
            cwd=snapshot.cwd,
            mode="tui",
        ),
        build_app=build_app,
        render_header=lambda: renderer.render_header(
            project_label=snapshot.project_label,
            cwd=snapshot.cwd,
            branch=snapshot.branch,
            session_label=snapshot.session_label,
            model_label=snapshot.model_label,
        ),
        trace=_trace,
        on_start=lambda: _trace_start(snapshot, interactive=False),
    )
    return await run_prepared_plain_conversation(
        prepared,
        stdin=stdin,
        stdout=stdout,
        prompt_runner=run_non_interactive_prompt_loop,
    )


def _screen_should_exit(text: str) -> bool:
    return isinstance(parse_conversation_intent(text), QuitIntent)


def _trace_start(snapshot: ConversationStartupView, *, interactive: bool) -> None:
    _trace(
        "tui.start",
        interactive=interactive,
        model=snapshot.model_label,
        cwd=snapshot.cwd,
        branch=snapshot.branch,
        session=snapshot.session_label,
    )


def _trace_resume_history(history: InstalledConversationHistory) -> None:
    _trace(
        "tui.resume_history",
        record_count=history.record_count,
        active_record_count=history.active_record_count,
        evicted_record_count=history.evicted_record_count,
        trimmed=history.trimmed,
    )


def _trace(name: str, **data: Any) -> None:
    log.debug_event("tui", name, **data)


async def _load_completion_provider(session: Any, *, base_path: Path | None) -> Any:
    try:
        return await coding_inline_completion_provider(session, base_path=base_path)
    except Exception as error:
        log.problem(
            "coding_ui_completion_provider_failed",
            source="tui",
            message=str(error) or error.__class__.__name__,
            recoverable=True,
            exc=error,
        )
        return CompletionProvider(())
