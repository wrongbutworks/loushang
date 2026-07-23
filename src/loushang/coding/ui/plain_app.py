from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.diagnostics.debug_status import debug_status_text
from loushang.coding.event.presentation_policy import is_cancelled_error_message
from loushang.coding.model_selection_tui import select_available_model
from loushang.coding.presentation.tui.plain import PlainCodingUiRenderer
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.coding.ui.product_binding import (
    build_coding_ui_controller,
    snapshot_coding_command_catalog,
)
from loushang.harnesstui.commands.interaction import CommandPaletteChooser
from loushang.harnesstui.conversation.agent_plain_app import (
    AgentPlainConversationPorts,
    build_agent_plain_conversation_app,
)
from loushang.harnesstui.conversation.info import InfoPanelPresenter
from loushang.harnesstui.conversation.plain_app import PlainConversationApp
from loushang.harnesstui.conversation.run_context import StableEmit, TraceFn
from loushang.harnesstui.selection.binding import (
    format_available_session_models,
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
    """Bind Coding content to the standard Agent plain conversation app."""

    controller = build_coding_ui_controller(
        runtime=runtime,
        session=session,
        verbose=verbose,
    )
    session_commands = getattr(session, "list_commands", None)
    command_catalog = CodingCommandCatalog(
        session_commands=session_commands if callable(session_commands) else None
    )

    async def snapshot_commands():
        return (await snapshot_coding_command_catalog(session)).commands()

    return build_agent_plain_conversation_app(
        ports=AgentPlainConversationPorts(
            session=session,
            renderer=renderer,
            event_renderer=event_renderer,
            stderr=stderr,
            verbose=verbose,
            cwd=cwd,
            emit=emit,
            trace=trace,
            now=now,
            controller=controller,
            command_effect=command_catalog.effect_for_route,
            snapshot_commands=snapshot_commands,
            select_model=lambda query, chooser: select_available_model(
                session,
                query=query,
                choose=chooser,
            ),
            format_models=lambda query: format_available_session_models(
                session,
                query=query,
            ),
            hotkeys=format_hotkeys,
            debug_status=lambda debug_path, scopes: debug_status_text(
                debug_path,
                scopes=scopes,
                cwd=cwd,
            ),
            enable_debug=enable_debug,
            disable_debug=disable_debug,
            suppress_cancelled_error=is_cancelled_error_message,
            settings_manager=getattr(session, "settings_manager", None),
            completion_provider=completion_provider,
            model_palette_chooser=model_palette_chooser,
            command_palette_chooser=command_palette_chooser,
            info_panel_presenter=info_panel_presenter,
        )
    )
