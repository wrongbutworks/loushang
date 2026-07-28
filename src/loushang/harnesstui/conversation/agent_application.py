"""Standard Agent bindings for prepared screen and plain applications."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, Protocol, TextIO, TypeVar

from loushang.harness.presentation import RenderableToolDefinition
from loushang.harness.session.model_selection import (
    get_session_model_identity,
    get_session_model_selection,
    model_identity_data,
)
from loushang.harnesstui.approval import build_permissions_surface_view
from loushang.harnesstui.commands.catalog import (
    ConversationCommandCatalog,
    snapshot_conversation_command_catalog,
)
from loushang.harnesstui.commands.presentation import format_commands
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
from loushang.harnesstui.conversation.plain_target import (
    PlainConversationProjectionPort,
)
from loushang.harnesstui.conversation.resume import (
    resume_hint_for_session,
    write_clean_exit_resume_hint,
)
from loushang.harnesstui.conversation.run_context import (
    InteractionContext,
    RebindableEventSource,
    StableEmit,
    TraceFn,
)
from loushang.harnesstui.conversation.runtime_view import (
    stable_string_queue_reader,
)
from loushang.harnesstui.conversation.screen_app import ScreenConversationApp
from loushang.harnesstui.conversation.session_view import (
    git_branch,
    is_running,
    session_cwd,
    session_label,
    session_observability_id,
    thinking_level,
)
from loushang.harnesstui.conversation.source import MaterializedTranscriptSource
from loushang.harnesstui.conversation.startup import (
    ConversationStartupView,
    build_conversation_startup_view,
)
from loushang.harnesstui.selection.binding import (
    SessionModelSelectorSurfaceProfile,
    build_session_model_selector_surface,
    format_available_session_models,
)
from loushang.harnesstui.status.persistence import (
    statusline_settings_from_store,
    statusline_settings_persistence_callback,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.harnesstui.surface.controller import ApprovalSurfaceDecision
from loushang.harnesstui.surface.factory import command_catalog_surface_view
from loushang.harnesstui.surface.view import ScreenSurfaceView
from loushang.harnesstui.surface.workflow import (
    ScreenSurfaceCommandCatalog,
    ScreenSurfaceForkResult,
    ScreenSurfaceWorkflowPorts,
    normalize_standard_conversation_interactive_command,
    normalize_standard_conversation_surface_command,
    strip_available_models_heading,
)
from loushang.tui.transcript import DisplayRecord

Cleanup = Callable[[], None]
SurfaceT = TypeVar("SurfaceT", bound=PreparedScreenSurfacePort)
AgentScreenApprovalHandler = Callable[[dict[str, object]], Awaitable[bool | None]]
PrepareAgentSession = Callable[[object], object | Awaitable[object]]


def _no_cleanup() -> None:
    return None


def _ignore_surface(_surface: SurfaceT) -> Cleanup:
    return _no_cleanup


async def load_agent_conversation_startup_view(
    *,
    runtime: object,
    session: object,
    prepare_session: PrepareAgentSession | None = None,
) -> ConversationStartupView:
    """Load standard startup facts from a structurally compatible Agent session."""

    if prepare_session is not None:
        prepared = prepare_session(session)
        if inspect.isawaitable(prepared):
            await prepared
    cwd = session_cwd(session=session, runtime=runtime)
    return build_conversation_startup_view(
        model_label=model_identity_data(
            await get_session_model_selection(session)
        ).label,
        cwd=cwd,
        branch=git_branch(cwd),
        session_label=session_label(session),
        session_observability_id=session_observability_id(session),
    )


@dataclass(frozen=True, slots=True)
class AgentScreenConversationApplicationBinding(Generic[SurfaceT]):
    """Prepare shared Agent screen state around Product UI components."""

    session: object
    app: ScreenConversationApp
    action_host: ConversationActionHost
    build_surface: Callable[[StatusProvider], SurfaceT]
    startup: ConversationStartupView
    interaction_context: InteractionContext
    profile: ConversationScreenRunProfile
    trace: TraceFn
    stdout: TextIO
    now: Callable[[], float]
    completion_provider: object | None = None
    bind_presenter: Callable[[SurfaceT], Cleanup] = _ignore_surface
    bind_transition: Callable[[SurfaceT], Cleanup] = _ignore_surface
    resume_command_prefix: tuple[str, ...] = ()
    session_provider: Callable[[], object] | None = None
    event_source: object | None = None

    def prepare(self) -> PreparedScreenConversationRun:
        session = self.session
        active_session = self.session_provider or (lambda: session)
        settings_manager = getattr(session, "settings_manager", None)

        def materialize_history() -> tuple[DisplayRecord, ...]:
            current = active_session()
            manager = getattr(current, "session_manager")
            tool_resolver = getattr(current, "get_tool_definition", None)
            return agent_session_history_records(
                manager.get_branch(),
                tool_definition_resolver=(
                    tool_resolver if callable(tool_resolver) else None
                ),
            )

        def resolve_tool(name: str) -> RenderableToolDefinition | None:
            resolver = getattr(active_session(), "get_tool_definition", None)
            return resolver(name) if callable(resolver) else None

        def read_pending(method_name: str) -> object:
            reader = getattr(active_session(), method_name, None)
            return reader() if callable(reader) else ()

        def refresh_session_label() -> None:
            self.app.state.session_label = session_label(active_session())
            self.app.request_render("product")

        status_provider = StatusProvider(
            model_label=self.startup.model_label,
            cwd=self.startup.cwd,
            branch=self.startup.branch,
            session_label=lambda: session_label(active_session()),
            thinking_level=lambda: thinking_level(active_session()),
            running=lambda: self.app.state.running or is_running(active_session()),
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
            event_source=self.event_source or session,
            event_listener_factory=lambda: (
                build_agent_screen_conversation_projection(
                    self.app,
                    tool_definition_resolver=resolve_tool,
                    read_pending_steers=stable_string_queue_reader(
                        lambda: read_pending("get_steering_messages")
                    ),
                    read_pending_followups=stable_string_queue_reader(
                        lambda: read_pending("get_follow_up_messages")
                    ),
                    on_session_info_changed=refresh_session_label,
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
                    active_session(),
                    command_prefix=self.resume_command_prefix,
                ),
            ),
        )


def build_agent_screen_surface_workflow_ports(
    session: object,
    *,
    session_provider: Callable[[], object] | None = None,
    select_model: Callable[[str], Awaitable[str]],
    set_model_label: Callable[[str], None],
    build_settings_content: Callable[[], Awaitable[object]],
    terminal_diagnostics: Callable[[], str],
    hotkeys: Callable[[], str],
    on_approval: AgentScreenApprovalHandler | None = None,
    build_resume_surface: Callable[[], ScreenSurfaceView] | None = None,
    activate_continuity: Callable[[object], Awaitable[str]] | None = None,
    build_delete_surface: Callable[[], ScreenSurfaceView] | None = None,
    delete_continuity: Callable[[object], Awaitable[str]] | None = None,
    build_fork_surface: Callable[[], ScreenSurfaceView] | None = None,
    fork_session: (
        Callable[[object], Awaitable[ScreenSurfaceForkResult]] | None
    ) = None,
    build_rename_surface: Callable[[], ScreenSurfaceView] | None = None,
    rename_session: Callable[[str | None], Awaitable[str]] | None = None,
    build_agent_tree_surface: Callable[[], ScreenSurfaceView] | None = None,
    build_side_question_surface: Callable[[str], ScreenSurfaceView] | None = None,
    command_catalog: ScreenSurfaceCommandCatalog | None = None,
    model_selector_profile: SessionModelSelectorSurfaceProfile = (
        SessionModelSelectorSurfaceProfile()
    ),
) -> ScreenSurfaceWorkflowPorts:
    """Bind a structural Agent session to the existing screen-surface workflow."""

    active_session = session_provider or (lambda: session)
    live_catalog = command_catalog or ConversationCommandCatalog()

    async def presentation_command_catalog() -> ScreenSurfaceCommandCatalog:
        if command_catalog is not None:
            return command_catalog
        return await snapshot_conversation_command_catalog(
            _agent_session_commands_provider(active_session())
        )

    async def format_session_commands(query: str) -> str:
        catalog = await presentation_command_catalog()
        return format_commands(catalog.commands(), query=query)

    async def build_command_selector():
        return command_catalog_surface_view(await presentation_command_catalog())

    async def refresh_model_label() -> None:
        label = (await get_session_model_identity(active_session())).label
        if label is not None:
            set_model_label(label)

    async def decide_approval(
        payload: ApprovalSurfaceDecision | None = None,
    ) -> bool | None:
        if on_approval is None:
            return True
        event: dict[str, object] = {}
        if payload is not None:
            event = {
                "action_id": payload.action_id,
                "action": payload.action,
                "approved": payload.approved,
                "scope": payload.scope,
                "raw_note": payload.raw_note,
            }
        return await on_approval(event)

    def build_permissions_surface() -> ScreenSurfaceView:
        getter = getattr(active_session(), "get_approval_permissions", None)
        if not callable(getter):
            raise RuntimeError("Session permissions are not available.")
        return build_permissions_surface_view(getter())

    async def apply_permission_action(action: str) -> bool:
        apply_action = getattr(
            active_session(),
            "apply_approval_permission_action",
            None,
        )
        if not callable(apply_action):
            return False
        result = apply_action(action)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    return ScreenSurfaceWorkflowPorts(
        select_model=select_model,
        refresh_model_label=refresh_model_label,
        command_catalog=live_catalog,
        normalize_command=normalize_standard_conversation_surface_command,
        format_models=lambda query: format_available_session_models(
            active_session(),
            query=query,
        ),
        models_info_body=strip_available_models_heading,
        format_commands=format_session_commands,
        build_model_selector=lambda: build_session_model_selector_surface(
            active_session(),
            profile=model_selector_profile,
        ),
        build_command_selector=build_command_selector,
        build_settings_content=build_settings_content,
        terminal_diagnostics=terminal_diagnostics,
        hotkeys=hotkeys,
        decide_approval=decide_approval,
        normalize_interactive_command=(
            normalize_standard_conversation_interactive_command
            if (
                build_resume_surface is not None
                or build_delete_surface is not None
                or build_fork_surface is not None
                or build_rename_surface is not None
            )
            else None
        ),
        build_resume_surface=build_resume_surface,
        activate_continuity=activate_continuity,
        build_delete_surface=build_delete_surface,
        delete_continuity=delete_continuity,
        build_fork_surface=build_fork_surface,
        fork_session=fork_session,
        build_rename_surface=build_rename_surface,
        rename_session=rename_session,
        build_agent_tree_surface=build_agent_tree_surface,
        build_permissions_surface=build_permissions_surface,
        apply_permission_action=apply_permission_action,
        build_side_question_surface=build_side_question_surface,
    )


def _agent_session_commands_provider(
    session: object,
) -> Callable[[], object] | None:
    getter = getattr(session, "list_commands", None)
    return getter if callable(getter) else None


class AgentScreenApprovalSurface(Protocol):
    """Approval controls supplied by an Agent conversation screen surface."""

    def open_approval(
        self,
        *,
        action: str,
        risk: str = "",
        requester: str = "",
        action_id: str | None = None,
        allow_session: bool = False,
    ) -> None: ...

    def dismiss_approval(self, action_id: str) -> None: ...

    def clear_approval_surfaces(self) -> None: ...


async def handle_agent_screen_approval(
    session: object,
    event: dict[str, object],
) -> bool:
    """Forward a screen approval decision to a supporting Agent session."""

    sink = getattr(session, "handle_screen_approval", None)
    if not callable(sink):
        return False
    result = sink(event)
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


def bind_agent_screen_approval_presenter(
    session: object,
    surface: AgentScreenApprovalSurface,
    *,
    session_provider: Callable[[], object] | None = None,
    default_action: str = "Approve tool call",
) -> Cleanup:
    """Bind an Agent session approval presenter to an existing screen surface."""

    setter = getattr(session, "set_approval_presenter", None)
    if not callable(setter):
        return _no_cleanup

    def present(payload: dict[str, object]) -> None:
        action = payload.get("action")
        risk = payload.get("risk")
        actor_id = payload.get("actor_id")
        action_id = payload.get("action_id")
        approval_options = payload.get("approval_options")
        allow_session = isinstance(approval_options, (list, tuple)) and (
            "allow_session" in approval_options
        )
        surface.open_approval(
            action=action if isinstance(action, str) else default_action,
            risk=risk if isinstance(risk, str) else "",
            requester=actor_id if isinstance(actor_id, str) else "",
            action_id=action_id if isinstance(action_id, str) else None,
            allow_session=allow_session,
        )

    setter(present, dismisser=surface.dismiss_approval)

    def unbind() -> None:
        target = session_provider() if session_provider is not None else session
        _unbind_agent_screen_approval_presenter(target)
        if target is not session:
            _unbind_agent_screen_approval_presenter(session)

    return unbind


def current_agent_runtime_session(runtime: object, fallback: object) -> object:
    """Resolve the current runtime session without depending on a Product host."""

    getter = getattr(runtime, "get_current_session", None)
    if callable(getter):
        current = getter()
        if current is not None:
            return current
    current = getattr(runtime, "current_session", None)
    return current if current is not None else fallback


def bind_agent_screen_session_transition(
    runtime: object,
    surface: AgentScreenApprovalSurface,
    *,
    on_rebind: Callable[[object], object | Awaitable[object]] | None = None,
) -> Cleanup:
    """Close transient surfaces before or after a runtime session transition."""

    subscribe = getattr(runtime, "subscribe_after_session_invalidate", None)
    if not callable(subscribe):
        subscribe = getattr(runtime, "subscribe_before_session_invalidate", None)
    if not callable(subscribe):
        unsubscribe = _no_cleanup
    else:
        subscribed = subscribe(lambda: _clear_agent_screen_surfaces(surface))
        unsubscribe = subscribed if callable(subscribed) else _no_cleanup

    set_rebind = getattr(runtime, "set_rebind_session", None)
    if callable(set_rebind) and on_rebind is not None:
        set_rebind(on_rebind)

    def cleanup() -> None:
        try:
            unsubscribe()
        finally:
            if callable(set_rebind) and on_rebind is not None:
                set_rebind(None)

    return cleanup


async def refresh_agent_screen_session(
    *,
    runtime: object,
    app: ScreenConversationApp,
    session: object,
    event_source: RebindableEventSource,
) -> None:
    """Install a newly active Agent session into an existing screen app."""

    snapshot = await load_agent_conversation_startup_view(
        runtime=runtime,
        session=session,
    )
    manager = getattr(session, "session_manager")
    tool_resolver = getattr(session, "get_tool_definition", None)
    history = agent_session_history_records(
        manager.get_branch(),
        tool_definition_resolver=(tool_resolver if callable(tool_resolver) else None),
    )
    app.state.model_label = snapshot.model_label
    app.state.cwd = snapshot.cwd
    app.state.branch = snapshot.branch
    app.state.session_label = snapshot.session_label
    app.replace_transcript_window(history, reason="resume")
    app.trim_active_transcript_window()
    event_source.rebind(session)
    app.request_render("product")


def _unbind_agent_screen_approval_presenter(session: object) -> None:
    host_unbind = getattr(session, "_unbind_approval_presenter_host", None)
    if callable(host_unbind):
        host_unbind()
        return
    setter = getattr(session, "set_approval_presenter", None)
    if callable(setter):
        setter(None)


def _clear_agent_screen_surfaces(surface: AgentScreenApprovalSurface) -> None:
    close = getattr(surface, "close_surface", None)
    if callable(close):
        close()
    surface.clear_approval_surfaces()


PlainAppFactory = Callable[
    [object, StableEmit],
    PlainConversationApp,
]


class AgentPlainConversationRenderer(
    PlainConversationRenderer,
    PlainConversationProjectionPort,
    Protocol,
):
    def render_header(
        self,
        *,
        project_label: str,
        cwd: str,
        branch: str | None,
        session_label: str | None,
        model_label: str | None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class AgentPlainConversationApplicationBinding:
    """Prepare shared Agent plain state around a Product renderer and app."""

    session: object
    renderer: AgentPlainConversationRenderer
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
    "AgentScreenApprovalHandler",
    "AgentScreenApprovalSurface",
    "AgentScreenConversationApplicationBinding",
    "PrepareAgentSession",
    "bind_agent_screen_approval_presenter",
    "bind_agent_screen_session_transition",
    "build_agent_screen_surface_workflow_ports",
    "current_agent_runtime_session",
    "handle_agent_screen_approval",
    "load_agent_conversation_startup_view",
    "refresh_agent_screen_session",
]
