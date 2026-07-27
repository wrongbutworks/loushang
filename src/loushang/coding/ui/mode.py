from __future__ import annotations

import time
from functools import partial
from pathlib import Path
from typing import Any, TextIO

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
from loushang.harnesstui.conversation.agent_application import (
    AgentPlainConversationApplicationBinding,
    AgentScreenConversationApplicationBinding,
    bind_agent_screen_approval_presenter,
    bind_agent_screen_session_transition,
    current_agent_runtime_session,
    handle_agent_screen_approval,
    refresh_agent_screen_session,
)
from loushang.harnesstui.conversation.application_host import (
    run_prepared_plain_conversation,
    run_prepared_screen_conversation,
)
from loushang.harnesstui.conversation.host import (
    run_action_host_conversation_screen,
)
from loushang.harnesstui.conversation.run_context import (
    RebindableEventSource,
    StableEmit,
)
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
    snapshot = await load_coding_tui_startup_view(runtime=runtime, session=session)
    app = ScreenCodingTuiApp(
        model_label=snapshot.model_label,
        cwd=snapshot.cwd,
        branch=snapshot.branch,
        session_label=snapshot.session_label,
        now=time.monotonic,
    )
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
    event_source = RebindableEventSource(session)
    surface_manager: ScreenSurfaceManager | None = None

    def no_rebound_presenter() -> None:
        return None

    rebound_presenter_cleanup = no_rebound_presenter

    def build_surface(status_provider):
        nonlocal surface_manager
        surface_manager = ScreenSurfaceManager(
            app=app,
            session=session,
            runtime=runtime,
            status_provider=status_provider,
            on_approval=lambda event: handle_agent_screen_approval(
                current_agent_runtime_session(runtime, session),
                event,
            ),
        )
        return surface_manager

    async def rebind_screen_session(next_session: object) -> None:
        nonlocal rebound_presenter_cleanup
        try:
            await refresh_agent_screen_session(
                runtime=runtime,
                app=app,
                session=next_session,
                event_source=event_source,
            )
        except Exception as refresh_error:
            event_source.rebind(next_session)
            app.replace_transcript_window((), reason="resume_refresh_failed")
            app.state.session_label = getattr(next_session, "session_name", None) or (
                getattr(next_session, "session_id", None)
            )
            app.add_error(
                "Session changed, but the TUI could not refresh its history.",
                str(refresh_error) or refresh_error.__class__.__name__,
            )
            log.problem(
                "coding_ui_session_rebind_failed",
                source="tui",
                message=str(refresh_error) or refresh_error.__class__.__name__,
                recoverable=True,
                exc=refresh_error,
            )
            return
        if event_source.last_rebind_error is not None:
            rebind_error = event_source.last_rebind_error
            app.add_error(
                "Session changed, but event subscription could not be rebound.",
                str(rebind_error) or rebind_error.__class__.__name__,
            )
            log.problem(
                "coding_ui_event_rebind_failed",
                source="tui",
                message=str(rebind_error) or rebind_error.__class__.__name__,
                recoverable=True,
                exc=rebind_error,
            )
        if surface_manager is None:  # pragma: no cover - prepared before rebind
            return
        try:
            surface_manager.status_provider.update_context(
                model_label=app.state.model_label,
                cwd=app.state.cwd,
                branch=app.state.branch,
            )
            app.composer.set_completion_provider(
                await _load_completion_provider(
                    next_session,
                    base_path=Path(app.state.cwd),
                )
            )
            rebound_presenter_cleanup()
            rebound_presenter_cleanup = bind_agent_screen_approval_presenter(
                next_session,
                surface_manager,
            )
        except Exception as error:
            app.add_error(
                "Session resumed, but some TUI bindings could not be refreshed.",
                str(error) or error.__class__.__name__,
            )
            log.problem(
                "coding_ui_session_binding_refresh_failed",
                source="tui",
                message=str(error) or error.__class__.__name__,
                recoverable=True,
                exc=error,
            )

    def bind_screen_presenter(surface):
        initial_cleanup = bind_agent_screen_approval_presenter(
            session,
            surface,
            session_provider=lambda: current_agent_runtime_session(runtime, session),
        )

        def cleanup() -> None:
            try:
                rebound_presenter_cleanup()
            finally:
                initial_cleanup()

        return cleanup

    prepared = AgentScreenConversationApplicationBinding(
        session=session,
        app=app,
        action_host=action_host,
        build_surface=build_surface,
        startup=snapshot,
        interaction_context=log_context(
            session_id=snapshot.session_observability_id,
            cwd=snapshot.cwd,
            mode="tui",
        ),
        profile=CODING_SCREEN_RUN_PROFILE,
        trace=_trace,
        stdout=stdout,
        now=time.monotonic,
        completion_provider=completion_provider,
        bind_presenter=bind_screen_presenter,
        bind_transition=lambda surface: bind_agent_screen_session_transition(
            runtime,
            surface,
            on_rebind=rebind_screen_session,
        ),
        resume_command_prefix=("loushang", "--resume"),
        session_provider=lambda: current_agent_runtime_session(runtime, session),
        event_source=event_source,
    ).prepare()
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
    renderer = PlainCodingUiRenderer(stdout=stdout, stderr=stderr, verbose=verbose)
    snapshot = await load_coding_tui_startup_view(runtime=runtime, session=session)

    def build_app(event_renderer: Any, emit: StableEmit):
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

    prepared = AgentPlainConversationApplicationBinding(
        session=session,
        renderer=renderer,
        startup=snapshot,
        interaction_context=log_context(
            session_id=snapshot.session_observability_id,
            cwd=snapshot.cwd,
            mode="tui",
        ),
        build_app=build_app,
        trace=_trace,
    ).prepare()
    return await run_prepared_plain_conversation(
        prepared,
        stdin=stdin,
        stdout=stdout,
        prompt_runner=run_non_interactive_prompt_loop,
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
