from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.commands.tui import (
    coding_command_palette,
    format_coding_commands,
)
from loushang.coding.interaction.intent import (
    CommandSelectIntent,
    CommandsIntent,
    HotkeysIntent,
    ModelSelectIntent,
    ModelsIntent,
    SettingsIntent,
    TerminalDiagnosticsIntent,
    parse_prompt_intent,
)
from loushang.coding.model_selection import (
    get_session_model_selection,
    iter_scoped_model_selections,
    model_label_from_selection,
)
from loushang.coding.model_selection_tui import (
    available_model_choices,
    current_model_choice_value,
    format_available_models,
    model_detail_descriptions_by_label,
    select_available_model,
)
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.settings_page import build_coding_settings_page
from loushang.harness.commands import CommandDef
from loushang.harnesstui.selection.catalog import (
    model_choice_select_items,
    model_label_select_items,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.harnesstui.surface.controller import ApprovalSurfaceDecision
from loushang.harnesstui.surface.factory import (
    command_palette_surface_view,
    model_selector_surface_view,
)
from loushang.harnesstui.surface.view import (
    ScreenSurfacePurpose as ScreenSurfacePurpose,
)
from loushang.harnesstui.surface.view import ScreenSurfaceView
from loushang.harnesstui.surface.workflow import (
    ScreenSurfaceCommand,
    ScreenSurfaceCommandCatalog,
    ScreenSurfaceWorkflow,
    ScreenSurfaceWorkflowCopy,
    ScreenSurfaceWorkflowPorts,
)


class ScreenSurfaceManager(ScreenSurfaceWorkflow):
    """Coding product adapter over the shared surface interaction host."""

    def __init__(
        self,
        *,
        app: ScreenCodingTuiApp,
        session: Any,
        status_provider: StatusProvider,
        on_approval: Callable[[dict[str, Any]], Awaitable[bool | None]] | None = None,
        command_catalog: ScreenSurfaceCommandCatalog | None = None,
    ) -> None:
        self.session = session
        self.status_provider = status_provider
        self.on_approval = on_approval
        self.command_catalog = command_catalog or CodingCommandCatalog(
            session_commands=_session_commands_provider(session)
        )
        super().__init__(
            app=app,
            ports=ScreenSurfaceWorkflowPorts(
                select_model=lambda value: select_available_model(
                    session,
                    query=value,
                ),
                refresh_model_label=self._refresh_model_label,
                set_command_text=app.composer.set_text,
                set_status=app.set_status,
                set_statusline_visible=app.set_statusline_visible,
                set_statusline_settings=app.set_statusline_settings,
                request_render=lambda: app.request_render("product"),
                command_catalog=self.command_catalog,
                normalize_command=_normalize_coding_surface_command,
                format_models=self._format_models,
                models_info_body=_models_info_body,
                format_commands=self._format_commands,
                build_model_selector=self._build_model_selector,
                build_command_selector=self._build_command_selector,
                build_settings_content=self._build_settings_content,
                terminal_diagnostics=self._terminal_diagnostics,
                hotkeys=format_hotkeys,
                decide_approval=self._decide_approval,
            ),
            copy=ScreenSurfaceWorkflowCopy(
                recoverable_error=_recoverable_surface_error,
                command_selected=lambda command: f"Command selected: {command}",
                approval_stale="Approval request is no longer pending",
                approval_confirmed=lambda action: f"Action confirmed: {action}",
                approval_rejected="Action rejected",
                models_title="Available Models",
                commands_title="Commands",
                terminal_title="Terminal",
                hotkeys_title="Hotkeys",
                settings_title="Settings",
            ),
        )

    @property
    def coding_app(self) -> ScreenCodingTuiApp:
        app = self.app
        if not isinstance(app, ScreenCodingTuiApp):  # pragma: no cover - constructor
            raise TypeError("Coding surface manager requires ScreenCodingTuiApp")
        return app

    def _list_command_catalog(self) -> CodingCommandCatalog | None:
        return (
            self.command_catalog
            if isinstance(self.command_catalog, CodingCommandCatalog)
            else None
        )

    async def _decide_approval(
        self, payload: ApprovalSurfaceDecision | None = None
    ) -> bool | None:
        callback_payload: dict[str, Any] = {}
        if payload is not None:
            callback_payload = {
                "action_id": payload.action_id,
                "action": payload.action,
                "approved": payload.approved,
                "raw_note": payload.raw_note,
            }
        if self.on_approval is None:
            return True
        return await self.on_approval(callback_payload)

    async def _format_models(self, query: str) -> str:
        return await format_available_models(self.session, query=query)

    async def _format_commands(self, query: str) -> str:
        return await format_coding_commands(
            self.session,
            query=query,
            command_catalog=self._list_command_catalog(),
        )

    async def _build_command_selector(self) -> ScreenSurfaceView:
        return command_palette_surface_view(
            await coding_command_palette(
                self.session,
                title="Commands",
                command_catalog=self._list_command_catalog(),
            ),
            title="Commands",
            purpose="command",
            max_visible=8,
        )

    async def _build_model_selector(self) -> ScreenSurfaceView:
        current_label = model_label_from_selection(
            await get_session_model_selection(self.session)
        )
        choices = await available_model_choices(self.session)
        current_value = await current_model_choice_value(self.session, choices=choices)
        scoped_selections = await iter_scoped_model_selections(self.session)
        scoped_labels = [
            label
            for selection in scoped_selections
            if (label := model_label_from_selection(selection)) is not None
        ]
        descriptions = await model_detail_descriptions_by_label(self.session)
        return model_selector_surface_view(
            all_items=model_choice_select_items(
                choices,
                current_value=current_value,
            ),
            scoped_items=model_label_select_items(
                scoped_labels,
                current_label=current_label,
                descriptions=descriptions,
            ),
            selected_value=current_value or current_label,
            title="Select Model",
            subtitle="Access legacy models by running loushang --model <provider/model>.",
            footer="  Press number or enter to confirm or esc to go back",
            presentation="bottom-exclusive",
            max_visible=10,
        )

    def _terminal_diagnostics(self) -> str:
        provider = self.coding_app.terminal_diagnostics_provider
        return (
            provider()
            if provider is not None
            else "Terminal diagnostics are not available outside an active TUI session."
        )

    async def _build_settings_content(self) -> object:
        return await build_coding_settings_page(
            session=self.session,
            status_provider=self.status_provider,
            settings_manager=getattr(self.session, "settings_manager", None),
            statusline_preview=self.coding_app.statusline_preview_snapshot,
        )

    async def _refresh_model_label(self) -> None:
        label = model_label_from_selection(
            await get_session_model_selection(self.session)
        )
        if label is not None:
            self.coding_app.state.model_label = label


def _normalize_coding_surface_command(
    text: str,
    command: CommandDef,
) -> ScreenSurfaceCommand | None:
    intent = parse_prompt_intent(text)
    if command.name == "model" and isinstance(intent, ModelSelectIntent):
        return ScreenSurfaceCommand("select_model", intent.query)
    if command.name == "models" and isinstance(intent, ModelsIntent):
        return ScreenSurfaceCommand("list_models", intent.query)
    if command.name == "command" and isinstance(intent, CommandSelectIntent):
        query = intent.query
        if query and not query.startswith("/"):
            query = f"/{query}"
        return ScreenSurfaceCommand("select_command", query)
    if command.name == "commands" and isinstance(intent, CommandsIntent):
        return ScreenSurfaceCommand("list_commands", intent.query)
    if command.name == "terminal" and isinstance(intent, TerminalDiagnosticsIntent):
        return ScreenSurfaceCommand("terminal_diagnostics")
    if command.name == "hotkeys" and isinstance(intent, HotkeysIntent):
        return ScreenSurfaceCommand("hotkeys")
    if command.name in {"settings", "config"} and isinstance(
        intent, SettingsIntent
    ):
        return ScreenSurfaceCommand("settings")
    return None


def _recoverable_surface_error(error: Exception) -> str:
    message = str(error).strip() or error.__class__.__name__
    return f"Error: {message}"


def _models_info_body(text: str) -> str:
    prefix = "Available models:\n"
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


def _session_commands_provider(session: Any) -> Callable[[], Any] | None:
    getter = getattr(session, "list_commands", None)
    if not callable(getter):
        return None
    return getter


__all__ = ["ScreenSurfaceManager", "ScreenSurfaceView"]
