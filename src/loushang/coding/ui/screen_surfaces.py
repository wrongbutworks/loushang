from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.ui.command_list import (
    coding_command_palette,
    format_coding_commands,
)
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.coding.ui.intent import (
    CommandSelectIntent,
    CommandsIntent,
    HotkeysIntent,
    ModelSelectIntent,
    ModelsIntent,
    SettingsIntent,
    TerminalDiagnosticsIntent,
    parse_prompt_intent,
)
from loushang.coding.ui.model import (
    get_session_model_selection,
    iter_scoped_model_selections,
    model_label_from_selection,
)
from loushang.coding.ui.model_list import (
    available_model_choices,
    current_model_choice_value,
    format_available_models,
    model_detail_descriptions_by_label,
    select_available_model,
)
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.settings_page import SettingsPageView
from loushang.coding.ui.status_provider import CodingTuiStatusProvider
from loushang.harness.commands import CommandDef, CommandKind
from loushang.harnesstui.commands.presentation import command_palette_select_items
from loushang.harnesstui.selection.catalog import (
    model_choice_select_items,
    model_label_select_items,
)
from loushang.harnesstui.selection.model import (
    MODEL_SELECTOR_SELECTED_STYLE as MODEL_SELECTOR_SELECTED_STYLE,
)
from loushang.harnesstui.selection.model import (
    ModelSelectorSurface,
)
from loushang.harnesstui.surface.controller import (
    ApprovalSurfaceDecision,
    ScreenSurfaceCoordinator,
)
from loushang.harnesstui.surface.factory import (
    command_surface_view,
    info_surface_view,
)
from loushang.harnesstui.surface.view import (
    ScreenSurfacePresentation,
    ScreenSurfaceView,
)
from loushang.harnesstui.surface.view import (
    ScreenSurfacePurpose as ScreenSurfacePurpose,
)
from loushang.tui import (
    CommandPalette,
    InputIntent,
)


class ScreenCommandCatalog(Protocol):
    def lookup(self, text: str) -> CommandDef | None: ...

    def commands(self) -> tuple[CommandDef, ...]: ...


@dataclass(slots=True)
class ScreenSurfaceManager:
    app: ScreenCodingTuiApp
    session: Any
    status_provider: CodingTuiStatusProvider
    on_approval: Callable[[dict[str, Any]], Awaitable[bool | None]] | None = None
    command_catalog: ScreenCommandCatalog | None = None
    _surface_coordinator: ScreenSurfaceCoordinator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._surface_coordinator = ScreenSurfaceCoordinator(
            app=self.app,
            handlers={
                "model": self._handle_model_submit,
                "command": self._handle_command_submit,
                "settings": self._handle_settings_submit,
                "dialog": self._handle_dialog_submit,
                "approval": self._handle_approval_submit,
            },
        )
        if self.command_catalog is None:
            self.command_catalog = CodingCommandCatalog(
                session_commands=_session_commands_provider(self.session)
            )

    def is_local_command(self, text: str) -> bool:
        return self._lookup_local_command(text) is not None

    async def handle_text(self, text: str) -> int | None:
        command = self._lookup_local_command(text)
        if command is None:
            return None
        intent = parse_prompt_intent(text)
        if command.name == "model" and isinstance(intent, ModelSelectIntent):
            await self._handle_model_intent(intent)
        elif command.name == "models" and isinstance(intent, ModelsIntent):
            models_text = await format_available_models(
                self.session, query=intent.query
            )
            self._open_info(
                "Available Models",
                _models_info_body(models_text),
                presentation="bottom-exclusive",
            )
        elif command.name == "command" and isinstance(intent, CommandSelectIntent):
            await self._handle_command_intent(intent)
        elif command.name == "commands" and isinstance(intent, CommandsIntent):
            self._open_info(
                "Commands",
                await format_coding_commands(
                    self.session,
                    query=intent.query,
                    command_catalog=self._list_command_catalog(),
                ),
            )
        elif command.name == "terminal" and isinstance(
            intent, TerminalDiagnosticsIntent
        ):
            self._open_terminal_diagnostics()
        elif command.name == "hotkeys" and isinstance(intent, HotkeysIntent):
            self._open_info("Hotkeys", format_hotkeys())
        elif command.name in {"settings", "config"} and isinstance(
            intent, SettingsIntent
        ):
            await self._open_settings()
        return None

    def _lookup_local_command(self, text: str) -> CommandDef | None:
        if self.command_catalog is None:
            return None
        command = self.command_catalog.lookup(text)
        if command is None or command.kind is not CommandKind.LOCAL_UI:
            return None
        return command

    def _list_command_catalog(self) -> CodingCommandCatalog | None:
        return (
            self.command_catalog
            if isinstance(self.command_catalog, CodingCommandCatalog)
            else None
        )

    async def handle_surface_intent(self, intent: InputIntent) -> int | None:
        return await self._surface_coordinator.handle_intent(intent)

    async def _handle_model_submit(self, payload: str) -> None:
        try:
            message = await select_available_model(self.session, query=payload)
        except Exception as error:
            self.app.set_status(_recoverable_surface_error(error))
            return
        self.close_surface()
        await self._refresh_model_label()
        self.app.set_status(message)

    async def _handle_command_submit(self, payload: str) -> None:
        command = payload.strip()
        if command:
            self.app.composer.set_text(command + (" " if " " not in command else ""))
            self.app.set_status(f"Command selected: {command}")
        self.close_surface()

    async def _handle_settings_submit(self, payload: dict[str, str]) -> None:
        surface = self._current_surface()
        page = surface.content if isinstance(surface, ScreenSurfaceView) else None
        apply_setting = getattr(page, "apply_setting", None)
        if not callable(apply_setting):
            return
        result = await apply_setting(payload["id"], payload.get("value", ""))
        if result.statusline_settings is not None:
            self.app.set_statusline_settings(result.statusline_settings)
        elif result.statusline_visible is not None:
            self.app.set_statusline_visible(result.statusline_visible)
        if result.refresh_model_label:
            await self._refresh_model_label()
        self.app.request_render("product")

    async def _handle_dialog_submit(self, _payload: Any | None = None) -> None:
        self.close_surface()

    async def _handle_approval_submit(
        self, payload: ApprovalSurfaceDecision | None = None
    ) -> None:
        callback_payload: dict[str, Any] = {}
        if payload is not None:
            callback_payload = {
                "action_id": payload.action_id,
                "action": payload.action,
                "approved": payload.approved,
                "raw_note": payload.raw_note,
            }
        accepted = True
        if self.on_approval is not None:
            accepted = await self.on_approval(callback_payload) is not False
        if not accepted:
            self.app.set_status("Approval request is no longer pending")
        elif payload is not None and payload.approved:
            self.app.set_status(f"Action confirmed: {payload.action}")
        elif payload is not None:
            self.app.set_status("Action rejected")

    def close_surface(self) -> None:
        self._surface_coordinator.close()

    def clear_approval_surfaces(self) -> None:
        self._surface_coordinator.clear_approvals()

    def dismiss_approval(self, action_id: str) -> None:
        self._surface_coordinator.dismiss_approval(action_id)

    async def _handle_model_intent(self, intent: ModelSelectIntent) -> None:
        if intent.query.strip():
            try:
                message = await select_available_model(self.session, query=intent.query)
            except Exception as error:
                self.app.set_status(_recoverable_surface_error(error))
            else:
                await self._refresh_model_label()
                self.app.set_status(message)
            return
        await self._open_model_selector()

    async def _handle_command_intent(self, intent: CommandSelectIntent) -> None:
        if intent.query.strip():
            command = (
                intent.query if intent.query.startswith("/") else f"/{intent.query}"
            )
            self.app.composer.set_text(command + " ")
            self.app.set_status(f"Command selected: {command}")
            return
        self._open_palette(
            "Commands",
            await coding_command_palette(
                self.session,
                title="Commands",
                command_catalog=self._list_command_catalog(),
            ),
            purpose="command",
        )

    def _open_palette(
        self,
        title: str,
        palette: CommandPalette,
        *,
        purpose: Literal["model", "command"],
    ) -> None:
        self._open_surface(
            command_surface_view(
                title=title,
                purpose=purpose,
                items=command_palette_select_items(palette),
                max_visible=8,
            )
        )

    async def _open_model_selector(self) -> None:
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
        surface = ModelSelectorSurface(
            all_items=tuple(
                model_choice_select_items(choices, current_value=current_value)
            ),
            scoped_items=tuple(
                model_label_select_items(
                    scoped_labels,
                    current_label=current_label,
                    descriptions=descriptions,
                )
            ),
            selected_value=current_value or current_label,
            max_visible=10,
        )
        self._open_surface(
            ScreenSurfaceView(
                title="Select Model",
                subtitle="Access legacy models by running loushang --model <provider/model>.",
                purpose="model",
                content=surface,
                footer="  Press number or enter to confirm or esc to go back",
                presentation="bottom-exclusive",
            )
        )

    def _open_info(
        self,
        title: str,
        text: str,
        *,
        presentation: ScreenSurfacePresentation = "bottom",
    ) -> None:
        self._open_surface(
            info_surface_view(
                title=title,
                text=text,
                presentation=presentation,
            )
        )

    def _open_terminal_diagnostics(self) -> None:
        provider = self.app.terminal_diagnostics_provider
        text = (
            provider()
            if provider is not None
            else "Terminal diagnostics are not available outside an active TUI session."
        )
        self._open_info("Terminal", text)

    async def _open_settings(self) -> None:
        surface = await SettingsPageView.create(
            session=self.session,
            status_provider=self.status_provider,
            settings_manager=getattr(self.session, "settings_manager", None),
            session_settings=getattr(self.session, "settings_controller", None),
            statusline_preview=self.app.statusline_preview_snapshot,
        )
        self._open_surface(
            ScreenSurfaceView(
                title="Settings",
                purpose="settings",
                content=surface,
                footer="",
                presentation="bottom-exclusive",
                preferred_height=24,
            )
        )

    def open_approval(
        self, *, action: str, risk: str = "", action_id: str | None = None
    ) -> None:
        self._surface_coordinator.present_approval(
            action=action,
            risk=risk,
            action_id=action_id,
        )

    def _open_surface(self, view: ScreenSurfaceView) -> None:
        self._surface_coordinator.open(view)

    def _current_surface(self) -> ScreenSurfaceView | Any | None:
        return self._surface_coordinator.current

    async def _refresh_model_label(self) -> None:
        label = model_label_from_selection(
            await get_session_model_selection(self.session)
        )
        if label is not None:
            self.app.state.model_label = label


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
