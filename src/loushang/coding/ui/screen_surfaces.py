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
    current_model_first,
    get_session_model_selection,
    iter_scoped_model_selections,
    model_label_from_selection,
)
from loushang.coding.ui.model_list import (
    ModelChoice,
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
from loushang.harnesstui.selection.model import (
    MODEL_SELECTOR_SELECTED_STYLE as MODEL_SELECTOR_SELECTED_STYLE,
)
from loushang.harnesstui.selection.model import (
    ModelSelectorSurface,
)
from loushang.harnesstui.surface.view import (
    ScreenSurfacePresentation,
    ScreenSurfaceView,
)
from loushang.harnesstui.surface.view import (
    ScreenSurfacePurpose as ScreenSurfacePurpose,
)
from loushang.tui import (
    ApprovalSurface,
    CommandPalette,
    CommandSurface,
    InfoPanel,
    InputIntent,
    SelectItem,
    Surface,
    SurfaceHandle,
)

SurfaceEventKind = Literal["surface_submit", "surface_close"]
SurfaceEventSource = Literal["model", "command", "settings", "dialog", "approval"]


class ScreenCommandCatalog(Protocol):
    def lookup(self, text: str) -> CommandDef | None: ...

    def commands(self) -> tuple[CommandDef, ...]: ...


@dataclass(frozen=True, slots=True)
class SurfaceEvent:
    kind: SurfaceEventKind
    source: SurfaceEventSource | None = None
    payload: Any = None


@dataclass(slots=True)
class ScreenSurfaceManager:
    app: ScreenCodingTuiApp
    session: Any
    status_provider: CodingTuiStatusProvider
    on_approval: Callable[[dict[str, Any]], Awaitable[bool | None]] | None = None
    command_catalog: ScreenCommandCatalog | None = None
    _handlers: dict[SurfaceEventSource, Callable[[Any], Awaitable[None]]] = field(
        init=False, repr=False
    )
    _active_overlay_view: ScreenSurfaceView | None = None
    _active_overlay_handle: SurfaceHandle | None = None
    _approval_queue: list[ApprovalSurface] = field(default_factory=list, repr=False)
    _approval_transitioning: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._handlers = {
            "model": self._handle_model_submit,
            "command": self._handle_command_submit,
            "settings": self._handle_settings_submit,
            "dialog": self._handle_dialog_submit,
            "approval": self._handle_approval_submit,
        }
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
        surface = self._current_surface()
        if not isinstance(surface, ScreenSurfaceView):
            return None

        event = self._normalize_surface_intent(intent, surface)
        if event is None:
            return None
        if event.kind == "surface_close":
            self.close_surface()
            return None
        if event.source is None:
            return None
        handler = self._handlers.get(event.source)
        if handler is None:
            return None
        await handler(event.payload)
        return None

    def _normalize_surface_intent(
        self, intent: InputIntent, surface: ScreenSurfaceView
    ) -> SurfaceEvent | None:
        if intent.kind in {"surface_close", "dialog_cancel"}:
            if surface.purpose == "approval":
                return _approval_surface_event(surface, approved=False)
            return SurfaceEvent(kind="surface_close", source=None)
        if surface.purpose == "model" and intent.kind in {"command", "select"}:
            return SurfaceEvent(
                kind="surface_submit", source="model", payload=intent.text
            )
        if surface.purpose == "command" and intent.kind in {"command", "select"}:
            return SurfaceEvent(
                kind="surface_submit", source="command", payload=intent.text
            )
        if surface.purpose == "settings" and intent.kind == "setting":
            return SurfaceEvent(
                kind="surface_submit",
                source="settings",
                payload={"id": intent.text, "value": intent.note},
            )
        if surface.purpose == "dialog" and intent.kind == "dialog_confirm":
            return SurfaceEvent(kind="surface_submit", source="dialog")
        if surface.purpose == "approval" and intent.kind in {"approve", "reject"}:
            return _approval_surface_event(
                surface,
                approved=intent.kind == "approve",
                note=intent.note,
            )
        return None

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
        self, payload: dict[str, Any] | None = None
    ) -> None:
        self._approval_transitioning = True
        self.close_surface()
        try:
            accepted = True
            if self.on_approval is not None:
                accepted = await self.on_approval(payload or {}) is not False
            if not accepted:
                self.app.set_status("Approval request is no longer pending")
            elif payload is not None and payload.get("approved"):
                self.app.set_status(f"Action confirmed: {payload.get('action')}")
            elif payload is not None:
                self.app.set_status("Action rejected")
        finally:
            self._approval_transitioning = False
            self._open_next_approval()

    def close_surface(self) -> None:
        if self._active_overlay_handle is not None:
            self._active_overlay_handle.close("closed")
        self._active_overlay_handle = None
        self._active_overlay_view = None
        self.app.active_surface = None

    def clear_approval_surfaces(self) -> None:
        self._approval_queue.clear()
        current = self._current_surface()
        if isinstance(current, ScreenSurfaceView) and current.purpose == "approval":
            self.close_surface()

    def dismiss_approval(self, action_id: str) -> None:
        current = self._current_surface()
        if (
            isinstance(current, ScreenSurfaceView)
            and current.purpose == "approval"
            and getattr(current.content, "action_id", None) == action_id
        ):
            self.close_surface()
            if not self._approval_transitioning:
                self._open_next_approval()
            return
        self._approval_queue = [
            approval
            for approval in self._approval_queue
            if approval.action_id != action_id
        ]

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
        surface = CommandSurface(_palette_items(palette), max_visible=8)
        self._open_surface(
            ScreenSurfaceView(title=title, purpose=purpose, content=surface)
        )

    async def _open_model_selector(self) -> None:
        current_label = model_label_from_selection(
            await get_session_model_selection(self.session)
        )
        choices = await available_model_choices(self.session)
        current_value = await current_model_choice_value(self.session, choices=choices)
        scoped_selections = await iter_scoped_model_selections(self.session)
        descriptions = await model_detail_descriptions_by_label(self.session)
        surface = ModelSelectorSurface(
            all_items=tuple(
                _model_choice_selector_items(choices, current_value=current_value)
            ),
            scoped_items=tuple(
                _model_selector_items(
                    scoped_selections,
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
            ScreenSurfaceView(
                title=title,
                purpose="info",
                content=InfoPanel.from_text(title=title, text=text, footer=""),
                footer="Enter/Esc to close",
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
        approval = ApprovalSurface(action=action, risk=risk, action_id=action_id)
        current = self._current_surface()
        if self._approval_transitioning or (
            isinstance(current, ScreenSurfaceView) and current.purpose == "approval"
        ):
            self._approval_queue.append(approval)
            return
        self._open_approval_surface(approval)

    def _open_approval_surface(self, approval: ApprovalSurface) -> None:
        self._open_surface(
            ScreenSurfaceView(
                title="Approval",
                purpose="approval",
                content=approval,
                footer="",
                presentation="bottom-exclusive",
            )
        )

    def _open_next_approval(self) -> None:
        if self._approval_queue:
            self._open_approval_surface(self._approval_queue.pop(0))

    def _open_surface(self, view: ScreenSurfaceView) -> None:
        self.close_surface()
        surface_host = self.app.surface_host
        if surface_host is None or view.exclusive_bottom:
            self.app.active_surface = view
            return
        self.app.active_surface = None
        self._active_overlay_view = view
        self._active_overlay_handle = surface_host.open_surface(
            Surface(
                renderable=view,
                focus_target=view,
                presentation="overlay",
                anchor="bottom-left",
                width="100%",
                max_height="80%",
            )
        )

    def _current_surface(self) -> ScreenSurfaceView | Any | None:
        return (
            self._active_overlay_view
            if self._active_overlay_view is not None
            else self.app.active_surface
        )

    async def _refresh_model_label(self) -> None:
        label = model_label_from_selection(
            await get_session_model_selection(self.session)
        )
        if label is not None:
            self.app.state.model_label = label


def _approval_surface_event(
    surface: ScreenSurfaceView,
    *,
    approved: bool,
    note: str | None = None,
) -> SurfaceEvent:
    action_id = getattr(surface.content, "action_id", None)
    action = getattr(surface.content, "action", None)
    return SurfaceEvent(
        kind="surface_submit",
        source="approval",
        payload={
            "action_id": action_id,
            "action": action,
            "approved": approved,
            "raw_note": note or action_id,
        },
    )


def _palette_items(palette: CommandPalette) -> list[SelectItem]:
    return [
        SelectItem(
            label=item.display_label(), value=item.value, description=item.description
        )
        for item in palette.items
    ]


def _model_selector_description(
    label: str, *, current_label: str | None, descriptions: dict[str, str]
) -> str:
    if label == current_label:
        return "current"
    return descriptions.get(label, "")


def _model_selector_items(
    selections: list[Any],
    *,
    current_label: str | None,
    descriptions: dict[str, str],
) -> list[SelectItem]:
    labels = current_model_first(
        [
            label
            for selection in selections
            if (label := model_label_from_selection(selection)) is not None
        ],
        current_label=current_label,
        label_of=lambda label: label,
    )
    ordinal_width = max(2, len(f"{len(labels)}."))
    items: list[SelectItem] = []
    for index, label in enumerate(labels, start=1):
        ordinal = f"{index}.".ljust(ordinal_width)
        items.append(
            SelectItem(
                label=f"{ordinal} {label}",
                value=label,
                description=_model_selector_description(
                    label, current_label=current_label, descriptions=descriptions
                ),
            )
        )
    return items


def _model_choice_selector_items(
    choices: list[ModelChoice],
    *,
    current_value: str | None,
) -> list[SelectItem]:
    ordinal_width = max(2, len(f"{len(choices)}."))
    items: list[SelectItem] = []
    for index, choice in enumerate(choices, start=1):
        ordinal = f"{index}.".ljust(ordinal_width)
        items.append(
            SelectItem(
                label=f"{ordinal} {choice.label}",
                value=choice.value,
                description=_model_choice_selector_description(
                    choice, current_value=current_value
                ),
            )
        )
    return items


def _model_choice_selector_description(
    choice: ModelChoice, *, current_value: str | None
) -> str:
    parts: list[str] = []
    if choice.value == current_value:
        parts.append("current")
    if choice.endpoint_id:
        parts.append(f"endpoint: {choice.endpoint_id}")
    if choice.region:
        parts.append(f"region: {choice.region}")
    if choice.lane:
        parts.append(f"lane: {choice.lane}")
    if choice.api:
        parts.append(f"protocol: {choice.api}")
    if choice.description:
        parts.append(choice.description)
    return " - ".join(parts)


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
