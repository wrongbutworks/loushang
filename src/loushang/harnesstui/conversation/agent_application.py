"""Standard Agent bindings for prepared screen and plain applications."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

from loushang.harnesstui.conversation.agent_binding import (
    agent_session_history_records,
    build_agent_plain_conversation_projection,
    build_agent_screen_conversation_projection,
)
from loushang.harnesstui.conversation.application_host import (
    InstalledConversationHistory,
    PreparedPlainConversationRun,
    PreparedScreenConversationRun,
    PreparedScreenSurfacePort,
)
from loushang.harnesstui.conversation.control import ConversationActionHost
from loushang.harnesstui.conversation.host import ConversationScreenRunProfile
from loushang.harnesstui.conversation.intents import (
    QuitIntent,
    parse_conversation_intent,
)
from loushang.harnesstui.conversation.plain_app import (
    PlainConversationApp,
    PlainConversationRenderer,
)
from loushang.harnesstui.conversation.resume import (
    resume_hint_for_session,
    write_clean_exit_resume_hint,
)
from loushang.harnesstui.conversation.run_context import (
    InteractionContext,
    StableEmit,
    TraceFn,
)
from loushang.harnesstui.conversation.runtime_view import (
    stable_string_queue_reader,
)
from loushang.harnesstui.conversation.screen_app import ScreenConversationApp
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
from loushang.tui.transcript import DisplayRecord

Cleanup = Callable[[], None]
SurfaceFactory = Callable[[StatusProvider], PreparedScreenSurfacePort]
SurfaceBinder = Callable[[PreparedScreenSurfacePort], Cleanup]


def _no_cleanup() -> None:
    return None


def _ignore_surface(_surface: PreparedScreenSurfacePort) -> Cleanup:
    return _no_cleanup


@dataclass(frozen=True, slots=True)
class AgentScreenConversationApplicationBinding:
    """Prepare shared Agent screen state around Product UI components."""

    session: object
    app: ScreenConversationApp
    action_host: ConversationActionHost
    build_surface: SurfaceFactory
    startup: ConversationStartupView
    interaction_context: InteractionContext
    profile: ConversationScreenRunProfile
    trace: TraceFn
    stdout: TextIO
    now: Callable[[], float]
    completion_provider: object | None = None
    bind_presenter: SurfaceBinder = _ignore_surface
    bind_transition: SurfaceBinder = _ignore_surface
    resume_command_prefix: tuple[str, ...] = ()

    def prepare(self) -> PreparedScreenConversationRun:
        session = self.session
        manager = getattr(session, "session_manager")
        tool_resolver = getattr(session, "get_tool_definition", None)
        settings_manager = getattr(session, "settings_manager", None)

        def materialize_history() -> tuple[DisplayRecord, ...]:
            return agent_session_history_records(
                manager.get_branch(),
                tool_definition_resolver=(
                    tool_resolver if callable(tool_resolver) else None
                ),
            )

        status_provider = StatusProvider(
            model_label=self.startup.model_label,
            cwd=self.startup.cwd,
            branch=self.startup.branch,
            session_label=lambda: session_label(session),
            thinking_level=lambda: thinking_level(session),
            running=lambda: self.app.state.running or is_running(session),
            statusline_settings=statusline_settings_from_store(settings_manager),
            on_statusline_settings_changed=(
                statusline_settings_persistence_callback(settings_manager)
            ),
        )
        self.app.set_statusline_settings(status_provider.statusline_settings())
        surface = self.build_surface(status_provider)
        history_records = materialize_history()

        return PreparedScreenConversationRun(
            app=self.app,
            action_host=self.action_host,
            surface=surface,
            event_source=session,
            event_listener_factory=lambda: (
                build_agent_screen_conversation_projection(
                    self.app,
                    tool_definition_resolver=(
                        tool_resolver if callable(tool_resolver) else None
                    ),
                    read_pending_steers=stable_string_queue_reader(
                        getattr(session, "get_steering_messages")
                    ),
                    read_pending_followups=stable_string_queue_reader(
                        getattr(session, "get_follow_up_messages")
                    ),
                    now=self.now,
                ).handle
            ),
            interaction_context=self.interaction_context,
            profile=self.profile,
            should_exit=_screen_should_exit,
            trace=self.trace,
            keybindings=(
                settings_manager.get_keybindings()
                if settings_manager is not None
                else None
            ),
            history_records=history_records,
            transcript_source_factory=lambda: MaterializedTranscriptSource(
                materialize_records=materialize_history,
                active_window_state=self.app.state,
            ),
            completion_provider=self.completion_provider,
            bind_presenter=lambda: self.bind_presenter(surface),
            bind_transition=lambda: self.bind_transition(surface),
            on_history_installed=lambda history: _trace_installed_history(
                self.trace, history
            ),
            on_start=lambda: _trace_start(self.trace, self.startup, interactive=True),
            on_clean_exit=lambda exit_code: write_clean_exit_resume_hint(
                stdout=self.stdout,
                exit_code=exit_code,
                hint=resume_hint_for_session(
                    session,
                    command_prefix=self.resume_command_prefix,
                ),
            ),
        )


PlainAppFactory = Callable[
    [object, StableEmit],
    PlainConversationApp,
]


@dataclass(frozen=True, slots=True)
class AgentPlainConversationApplicationBinding:
    """Prepare shared Agent plain state around a Product renderer and app."""

    session: object
    renderer: PlainConversationRenderer
    startup: ConversationStartupView
    interaction_context: InteractionContext
    build_app: PlainAppFactory
    trace: TraceFn

    def prepare(self) -> PreparedPlainConversationRun:
        event_renderer = build_agent_plain_conversation_projection(
            self.renderer,
            tool_definition_resolver=getattr(self.session, "get_tool_definition", None),
        )
        return PreparedPlainConversationRun(
            event_source=self.session,
            event_listener=event_renderer.handle,
            interaction_context=self.interaction_context,
            build_app=lambda emit: self.build_app(event_renderer, emit),
            render_header=lambda: self.renderer.render_header(
                project_label=self.startup.project_label,
                cwd=self.startup.cwd,
                branch=self.startup.branch,
                session_label=self.startup.session_label,
                model_label=self.startup.model_label,
            ),
            trace=self.trace,
            on_start=lambda: _trace_start(self.trace, self.startup, interactive=False),
        )


def _screen_should_exit(text: str) -> bool:
    return isinstance(parse_conversation_intent(text), QuitIntent)


def _trace_start(
    trace: TraceFn,
    startup: ConversationStartupView,
    *,
    interactive: bool,
) -> None:
    trace(
        "tui.start",
        interactive=interactive,
        model=startup.model_label,
        cwd=startup.cwd,
        branch=startup.branch,
        session=startup.session_label,
    )


def _trace_installed_history(
    trace: TraceFn,
    history: InstalledConversationHistory,
) -> None:
    trace(
        "tui.resume_history",
        record_count=history.record_count,
        active_record_count=history.active_record_count,
        evicted_record_count=history.evicted_record_count,
        trimmed=history.trimmed,
    )


__all__ = [
    "AgentPlainConversationApplicationBinding",
    "AgentScreenConversationApplicationBinding",
]
