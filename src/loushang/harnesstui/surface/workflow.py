from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from loushang.harness.commands import CommandDef, CommandKind
from loushang.harnesstui.settings.workflow import SettingsApplyResult
from loushang.harnesstui.status.line import StatusLineSettings
from loushang.harnesstui.surface.controller import (
    ApprovalSurfaceDecision,
    ScreenSurfaceAppPort,
    ScreenSurfaceCoordinator,
)
from loushang.harnesstui.surface.factory import info_surface_view
from loushang.harnesstui.surface.view import (
    ScreenSurfacePresentation,
    ScreenSurfaceView,
)
from loushang.tui import InputIntent

ScreenSurfaceCommandKind = Literal[
    "select_model",
    "list_models",
    "select_command",
    "list_commands",
    "terminal_diagnostics",
    "hotkeys",
    "settings",
]

ModelSelectionHandler = Callable[[str], Awaitable[str]]
ModelLabelRefresher = Callable[[], Awaitable[None]]
ApprovalDecisionHandler = Callable[
    [ApprovalSurfaceDecision | None], Awaitable[bool | None]
]


class ScreenSurfaceCommandCatalog(Protocol):
    def lookup(self, text: str) -> CommandDef | None: ...

    def commands(self) -> tuple[CommandDef, ...]: ...


@dataclass(frozen=True, slots=True)
class ScreenSurfaceCommand:
    """Product-normalized local command consumed by the surface host."""

    kind: ScreenSurfaceCommandKind
    query: str = ""


@dataclass(frozen=True, slots=True)
class ScreenSurfaceWorkflowCopy:
    """Product copy used by the shared surface interaction workflow."""

    recoverable_error: Callable[[Exception], str]
    command_selected: Callable[[str], str]
    approval_stale: str
    approval_confirmed: Callable[[str | None], str]
    approval_rejected: str
    models_title: str
    commands_title: str
    terminal_title: str
    hotkeys_title: str
    settings_title: str


@dataclass(frozen=True, slots=True)
class ScreenSurfaceWorkflowPorts:
    """Product effects required by generic surface submissions."""

    select_model: ModelSelectionHandler
    refresh_model_label: ModelLabelRefresher
    set_command_text: Callable[[str], None]
    set_status: Callable[[str], None]
    set_statusline_visible: Callable[[bool], None]
    set_statusline_settings: Callable[[StatusLineSettings], None]
    request_render: Callable[[], None]
    command_catalog: ScreenSurfaceCommandCatalog
    normalize_command: Callable[[str, CommandDef], ScreenSurfaceCommand | None]
    format_models: Callable[[str], Awaitable[str]]
    models_info_body: Callable[[str], str]
    format_commands: Callable[[str], Awaitable[str]]
    build_model_selector: Callable[[], Awaitable[ScreenSurfaceView]]
    build_command_selector: Callable[[], Awaitable[ScreenSurfaceView]]
    build_settings_content: Callable[[], Awaitable[object]]
    terminal_diagnostics: Callable[[], str]
    hotkeys: Callable[[], str]
    decide_approval: ApprovalDecisionHandler | None = None


@dataclass(slots=True)
class ScreenSurfaceWorkflow:
    """Run product-neutral submit, close, and approval surface mechanics."""

    app: ScreenSurfaceAppPort
    ports: ScreenSurfaceWorkflowPorts
    copy: ScreenSurfaceWorkflowCopy
    coordinator: ScreenSurfaceCoordinator = field(init=False)

    def __post_init__(self) -> None:
        self.coordinator = ScreenSurfaceCoordinator(
            app=self.app,
            handlers={
                "model": self._handle_model_submit,
                "command": self._handle_command_submit,
                "settings": self._handle_settings_submit,
                "dialog": self._handle_dialog_submit,
                "approval": self._handle_approval_submit,
            },
        )

    @property
    def current(self) -> ScreenSurfaceView | object | None:
        return self.coordinator.current

    async def handle_intent(self, intent: InputIntent) -> int | None:
        return await self.coordinator.handle_intent(intent)

    async def handle_surface_intent(self, intent: InputIntent) -> int | None:
        return await self.handle_intent(intent)

    def is_local_command(self, text: str) -> bool:
        return self._resolve_command(text) is not None

    async def handle_text(self, text: str) -> int | None:
        command = self._resolve_command(text)
        if command is None:
            return None
        if command.kind == "select_model":
            if command.query.strip():
                await self.select_model(command.query, close_surface=False)
            else:
                self.open(await self.ports.build_model_selector())
        elif command.kind == "list_models":
            models = await self.ports.format_models(command.query)
            self.open_info(
                title=self.copy.models_title,
                text=self.ports.models_info_body(models),
                presentation="bottom-exclusive",
            )
        elif command.kind == "select_command":
            if command.query.strip():
                self.select_command(command.query, close_surface=False)
            else:
                self.open(await self.ports.build_command_selector())
        elif command.kind == "list_commands":
            self.open_info(
                title=self.copy.commands_title,
                text=await self.ports.format_commands(command.query),
                presentation="bottom",
            )
        elif command.kind == "terminal_diagnostics":
            self.open_info(
                title=self.copy.terminal_title,
                text=self.ports.terminal_diagnostics(),
                presentation="bottom",
            )
        elif command.kind == "hotkeys":
            self.open_info(
                title=self.copy.hotkeys_title,
                text=self.ports.hotkeys(),
                presentation="bottom",
            )
        elif command.kind == "settings":
            self.open_settings(
                title=self.copy.settings_title,
                content=await self.ports.build_settings_content(),
                presentation="bottom-exclusive",
                preferred_height=24,
            )
        return None

    async def select_model(self, value: str, *, close_surface: bool) -> None:
        try:
            message = await self.ports.select_model(value)
        except Exception as error:
            self.ports.set_status(self.copy.recoverable_error(error))
            return
        if close_surface:
            self.close()
        await self.ports.refresh_model_label()
        self.ports.set_status(message)

    def select_command(self, value: str, *, close_surface: bool) -> None:
        command = value.strip()
        if command:
            self.ports.set_command_text(command + " ")
            self.ports.set_status(self.copy.command_selected(command))
        if close_surface:
            self.close()

    def open(self, view: ScreenSurfaceView) -> None:
        self.coordinator.open(view)

    def open_info(
        self,
        *,
        title: str,
        text: str,
        presentation: ScreenSurfacePresentation,
    ) -> None:
        self.open(
            info_surface_view(
                title=title,
                text=text,
                presentation=presentation,
            )
        )

    def open_settings(
        self,
        *,
        title: str,
        content: object,
        presentation: ScreenSurfacePresentation,
        preferred_height: int,
    ) -> None:
        self.open(
            ScreenSurfaceView(
                title=title,
                purpose="settings",
                content=content,
                footer="",
                presentation=presentation,
                preferred_height=preferred_height,
            )
        )

    def close(self) -> None:
        self.coordinator.close()

    def close_surface(self) -> None:
        self.close()

    def present_approval(
        self,
        *,
        action: str,
        risk: str = "",
        action_id: str | None = None,
    ) -> None:
        self.coordinator.present_approval(
            action=action,
            risk=risk,
            action_id=action_id,
        )

    def open_approval(
        self,
        *,
        action: str,
        risk: str = "",
        action_id: str | None = None,
    ) -> None:
        self.present_approval(action=action, risk=risk, action_id=action_id)

    def clear_approvals(self) -> None:
        self.coordinator.clear_approvals()

    def clear_approval_surfaces(self) -> None:
        self.clear_approvals()

    def dismiss_approval(self, action_id: str) -> None:
        self.coordinator.dismiss_approval(action_id)

    async def _handle_model_submit(self, payload: str) -> None:
        await self.select_model(payload, close_surface=True)

    async def _handle_command_submit(self, payload: str) -> None:
        self.select_command(payload, close_surface=True)

    async def _handle_settings_submit(self, payload: dict[str, str]) -> None:
        surface = self.current
        page = surface.content if isinstance(surface, ScreenSurfaceView) else None
        apply_setting = getattr(page, "apply_setting", None)
        if not callable(apply_setting):
            return
        result: SettingsApplyResult = await apply_setting(
            payload["id"], payload.get("value", "")
        )
        if result.statusline_settings is not None:
            self.ports.set_statusline_settings(result.statusline_settings)
        elif result.statusline_visible is not None:
            self.ports.set_statusline_visible(result.statusline_visible)
        if result.refresh_model_label:
            await self.ports.refresh_model_label()
        self.ports.request_render()

    async def _handle_dialog_submit(self, _payload: Any | None = None) -> None:
        self.close()

    async def _handle_approval_submit(
        self, payload: ApprovalSurfaceDecision | None = None
    ) -> None:
        accepted = True
        if self.ports.decide_approval is not None:
            accepted = await self.ports.decide_approval(payload) is not False
        if not accepted:
            self.ports.set_status(self.copy.approval_stale)
        elif payload is not None and payload.approved:
            self.ports.set_status(self.copy.approval_confirmed(payload.action))
        elif payload is not None:
            self.ports.set_status(self.copy.approval_rejected)

    def _resolve_command(self, text: str) -> ScreenSurfaceCommand | None:
        command = self.ports.command_catalog.lookup(text)
        if command is None or command.kind is not CommandKind.LOCAL_UI:
            return None
        return self.ports.normalize_command(text, command)


__all__ = [
    "ApprovalDecisionHandler",
    "ModelLabelRefresher",
    "ModelSelectionHandler",
    "ScreenSurfaceWorkflow",
    "ScreenSurfaceWorkflowCopy",
    "ScreenSurfaceWorkflowPorts",
    "ScreenSurfaceCommand",
    "ScreenSurfaceCommandCatalog",
    "ScreenSurfaceCommandKind",
]
