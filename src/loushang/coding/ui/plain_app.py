from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.commands.tui import (
    CommandPaletteChooser,
    format_coding_commands,
    select_coding_command,
)
from loushang.coding.diagnostics.tui import DebugCommandHandler
from loushang.coding.event.presentation_policy import is_cancelled_error_message
from loushang.coding.interaction.controller import CodingUiController
from loushang.coding.interaction.intent import AbortIntent
from loushang.coding.interaction.tui_profile import (
    CodingTuiPorts,
    CodingTuiProfile,
    is_coding_work_intent,
)
from loushang.coding.model_selection_tui import (
    ModelPaletteChooser,
    format_available_models,
    select_available_model,
)
from loushang.coding.presentation.session import (
    is_running,
    session_error_message,
    session_label,
    thinking_level,
)
from loushang.coding.presentation.tui.plain import PlainCodingUiRenderer
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.harnesstui.conversation.control import (
    ConversationRunControl,
    ConversationTextAction,
)
from loushang.harnesstui.conversation.info import (
    ConversationInfoPresenter,
    InfoPanelPresenter,
)
from loushang.harnesstui.conversation.plain_app import (
    PlainConversationApp,
    build_plain_conversation_app,
)
from loushang.harnesstui.conversation.queue import (
    pending_queue_view,
    restore_queued_messages,
)
from loushang.harnesstui.conversation.run_context import StableEmit, TraceFn
from loushang.harnesstui.status.persistence import (
    statusline_settings_from_store,
    statusline_settings_persistence_callback,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.tui import CompletionProvider


def build_plain_coding_tui_app(
    *,
    runtime: Any,
    session: Any,
    renderer: PlainCodingUiRenderer,
    event_renderer: Any,
    stderr: TextIO,
    verbose: bool,
    model_label: str | None,
    cwd: str,
    branch: str | None,
    emit: StableEmit,
    trace: TraceFn,
    now: Callable[[], float],
    enable_debug: Callable[..., Path],
    disable_debug: Callable[[], None],
    completion_provider: CompletionProvider | None = None,
    model_palette_chooser: ModelPaletteChooser | None = None,
    command_palette_chooser: CommandPaletteChooser | None = None,
    info_panel_presenter: InfoPanelPresenter | None = None,
) -> PlainConversationApp:
    lifecycle = ConversationRunControl()
    controller = CodingUiController(runtime=runtime, session=session, verbose=verbose)
    debug_command = DebugCommandHandler(
        session=session,
        cwd=cwd,
        renderer=renderer,
        emit=emit,
        trace=trace,
        enable=enable_debug,
        disable=disable_debug,
    )
    settings_manager = getattr(session, "settings_manager", None)
    status_provider = StatusProvider(
        model_label=model_label,
        cwd=cwd,
        branch=branch,
        session_label=lambda: session_label(session),
        thinking_level=lambda: thinking_level(session),
        running=lambda: lifecycle.visible_running(session_running=is_running(session)),
        statusline_settings=statusline_settings_from_store(settings_manager),
        on_statusline_settings_changed=statusline_settings_persistence_callback(
            settings_manager
        ),
    )
    session_commands = getattr(session, "list_commands", None)
    profile = CodingTuiProfile(
        lifecycle=lifecycle,
        command_catalog=CodingCommandCatalog(
            session_commands=session_commands if callable(session_commands) else None
        ),
        session_running=lambda: is_running(session),
        trace=trace,
    )
    coding_ports = CodingTuiPorts(
        debug=debug_command.handle,
        model_select=lambda query: select_available_model(
            session, query=query, choose=model_palette_chooser
        ),
        models=lambda query: format_available_models(session, query=query),
        command_select=lambda query: select_coding_command(
            session, query=query, choose=command_palette_chooser
        ),
        commands=lambda query: format_coding_commands(session, query=query),
        hotkeys=format_hotkeys,
        settings_text=status_provider.settings_summary_text,
        info=ConversationInfoPresenter(
            emit=emit,
            render_status=renderer.render_status,
            render_panel=getattr(renderer, "render_info_panel", None),
            present_panel=info_panel_presenter,
        ),
    )

    async def abort_settling(_action: ConversationTextAction, _intent) -> None:
        await emit(
            lambda: renderer.render_status(
                "Abort in progress. Wait for the current request to settle."
            ),
            label="abort:pending_input",
        )

    def suppress_cancelled(outcome, error_message: str | None) -> bool:
        if (
            outcome.run_id is not None
            and lifecycle.aborted_id == outcome.run_id
            and is_cancelled_error_message(error_message)
        ):
            lifecycle.clear_aborted(outcome.run_id)
            trace(
                "prompt.suppressed_cancelled",
                run_id=outcome.run_id,
                error_message=error_message,
            )
            return True
        return False

    return build_plain_conversation_app(
        lifecycle=lifecycle,
        profile=profile.host_profile(now=now),
        controller=controller,
        renderer=renderer,
        emit=emit,
        trace=trace,
        session_running=lambda: is_running(session),
        abort_action=lambda: controller.dispatch(AbortIntent()),
        abort_settling=abort_settling,
        is_work_intent=is_coding_work_intent,
        local=coding_ports.local,
        resolve_error=lambda outcome: (
            outcome.result.error_message or session_error_message(session)
        ),
        suppress_result=suppress_cancelled,
        stderr=stderr,
        verbose=verbose,
        last_error_message=lambda: event_renderer.last_error_message,
        now=now,
        restore_queue=lambda text: restore_queued_messages(
            session,
            text,
            trace=trace,
        ),
        pending_messages=lambda: pending_queue_view(session),
        idle_follow_up_message="Follow-up is only available while a run is active.",
        queued_follow_up_message="Follow-up queued.",
        completion_provider=completion_provider,
    )
