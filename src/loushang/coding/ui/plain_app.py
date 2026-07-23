from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.diagnostics.debug_status import debug_status_text
from loushang.coding.event.presentation_policy import is_cancelled_error_message
from loushang.coding.interaction.controller import CodingUiController
from loushang.coding.interaction.intent import AbortIntent, CodingUiIntent
from loushang.coding.interaction.tui_profile import (
    CodingLocalAction,
    CodingTuiPorts,
    build_coding_tui_host_profile,
    is_coding_work_intent,
    snapshot_coding_command_catalog,
)
from loushang.coding.model_selection_tui import select_available_model
from loushang.coding.presentation.session import (
    is_running,
    session_error_message,
)
from loushang.coding.presentation.tui.plain import PlainCodingUiRenderer
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.harness.commands import CommandDef
from loushang.harnesstui.commands.interaction import (
    CommandInteractionPresentationCopy,
    CommandInteractionSnapshot,
    CommandPaletteChooser,
    present_command_interaction,
    run_command_interaction,
)
from loushang.harnesstui.commands.presentation import (
    command_completion_item,
    format_commands,
)
from loushang.harnesstui.conversation.debug_action import (
    DebugActionCopy,
    DebugActionHandler,
    DebugActionPorts,
)
from loushang.harnesstui.conversation.info import InfoPanelPresenter
from loushang.harnesstui.conversation.plain_app import (
    PlainConversationApp,
    PlainConversationAssembly,
    PlainConversationPorts,
    PlainConversationProductBinding,
    PlainConversationProfile,
    build_plain_conversation_app,
)
from loushang.harnesstui.conversation.queue import (
    pending_queue_view,
    restore_queued_messages,
)
from loushang.harnesstui.conversation.run_context import StableEmit, TraceFn
from loushang.harnesstui.selection.binding import (
    format_available_session_models as format_available_models,
)
from loushang.harnesstui.selection.interaction import ModelInteractionChooser
from loushang.tui import CompletionProvider


def build_plain_coding_tui_app(
    *,
    runtime: Any,
    session: Any,
    renderer: PlainCodingUiRenderer,
    event_renderer: Any,
    stderr: TextIO,
    verbose: bool,
    cwd: str,
    emit: StableEmit,
    trace: TraceFn,
    now: Callable[[], float],
    enable_debug: Callable[..., Path],
    disable_debug: Callable[[], None],
    completion_provider: CompletionProvider | None = None,
    model_palette_chooser: ModelInteractionChooser | None = None,
    command_palette_chooser: CommandPaletteChooser | None = None,
    info_panel_presenter: InfoPanelPresenter | None = None,
) -> PlainConversationApp:
    settings_manager = getattr(session, "settings_manager", None)

    def bind_product(
        assembly: PlainConversationAssembly,
    ) -> PlainConversationProductBinding[CodingUiIntent, CodingLocalAction]:
        controller = CodingUiController(
            runtime=runtime,
            session=session,
            verbose=verbose,
        )
        debug_action = DebugActionHandler[Path](
            copy=DebugActionCopy(
                enabled_status=lambda debug_path, scopes: debug_status_text(
                    debug_path,
                    scopes=scopes,
                    cwd=cwd,
                ),
                disabled_status="Debug logging disabled.",
                enabled_emit_label="debug:enabled",
                disabled_emit_label="debug:disabled",
            ),
            ports=DebugActionPorts(
                enable=lambda scopes: enable_debug(session=session, scopes=scopes),
                disable=disable_debug,
                on_enabled=lambda debug_path, scopes: trace(
                    "debug.enabled",
                    path=str(debug_path),
                    scopes=list(scopes),
                ),
                on_disabled=lambda: trace("debug.disabled"),
                emit=emit,
                render_status=renderer.render_status,
            ),
        )
        session_commands = getattr(session, "list_commands", None)
        command_catalog = CodingCommandCatalog(
            session_commands=session_commands if callable(session_commands) else None
        )

        async def select_command(query: str) -> str:
            snapshot = await snapshot_coding_command_catalog(session)
            result = await run_command_interaction(
                CommandInteractionSnapshot(snapshot.commands()),
                query=query,
                choose=command_palette_chooser,
            )
            return present_command_interaction(
                result,
                copy=_CODING_COMMAND_INTERACTION_COPY,
            )

        async def list_commands(query: str) -> str:
            snapshot = await snapshot_coding_command_catalog(session)
            return format_commands(snapshot.commands(), query=query)

        return PlainConversationProductBinding(
            host_profile=build_coding_tui_host_profile(
                lifecycle=assembly.lifecycle,
                command_catalog=command_catalog,
                session_running=lambda: is_running(session),
                trace=trace,
                now=now,
            ),
            controller=controller,
            abort_action=lambda: controller.dispatch(AbortIntent()),
            is_work_intent=is_coding_work_intent,
            local=CodingTuiPorts(
                debug=lambda intent: debug_action.handle(
                    enabled=intent.enabled,
                    scopes=intent.scopes,
                ),
                model_select=lambda query: select_available_model(
                    session, query=query, choose=model_palette_chooser
                ),
                models=lambda query: format_available_models(session, query=query),
                command_select=select_command,
                commands=list_commands,
                hotkeys=format_hotkeys,
                settings_text=assembly.settings_text,
                info=assembly.info,
            ).local,
            fallback_error_message=lambda: session_error_message(session),
            suppress_aborted_error=is_cancelled_error_message,
        )

    return build_plain_conversation_app(
        profile=PlainConversationProfile(
            statusline_settings_store=settings_manager,
            abort_settling_message=(
                "Abort in progress. Wait for the current request to settle."
            ),
            idle_follow_up_message=(
                "Follow-up is only available while a run is active."
            ),
            queued_follow_up_message="Follow-up queued.",
            traceback_enabled=verbose,
            now=now,
        ),
        ports=PlainConversationPorts(
            bind_product=bind_product,
            renderer=renderer,
            emit=emit,
            trace=trace,
            stderr=stderr,
            session_running=lambda: is_running(session),
            last_error_message=lambda: event_renderer.last_error_message,
            restore_queue=lambda text: restore_queued_messages(
                session,
                text,
                trace=trace,
            ),
            pending_messages=lambda: pending_queue_view(session),
            render_info_panel=getattr(renderer, "render_info_panel", None),
            present_info_panel=info_panel_presenter,
            completion_provider=completion_provider,
        ),
    )


def _command_value(item: CommandDef) -> str:
    completion = command_completion_item(item)
    return completion.value if completion is not None else ""


_CODING_COMMAND_INTERACTION_COPY = CommandInteractionPresentationCopy[CommandDef](
    list_items=format_commands,
    item_text=_command_value,
    cancelled="Command selection cancelled.",
    empty="No commands available.",
    no_match=lambda query: f"No commands match: {query}",
    ambiguous_title="Multiple commands match:",
    ambiguous_hint="Use /command <full command> to select one.",
    selected_prefix="Command selected: ",
)
