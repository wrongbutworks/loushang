from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.model_selection_tui import select_available_model
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.coding.ui.product_binding import snapshot_coding_command_catalog
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.settings_page import build_coding_settings_page
from loushang.harness.session.model_selection import (
    get_session_model_identity,
)
from loushang.harnesstui.commands.presentation import format_commands
from loushang.harnesstui.selection.binding import (
    SessionModelSelectorSurfaceProfile,
    build_session_model_selector_surface,
)
from loushang.harnesstui.selection.binding import (
    format_available_session_models as format_available_models,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.harnesstui.surface.controller import ApprovalSurfaceDecision
from loushang.harnesstui.surface.factory import command_catalog_surface_view
from loushang.harnesstui.surface.view import ScreenSurfaceView
from loushang.harnesstui.surface.workflow import (
    STANDARD_SCREEN_SURFACE_WORKFLOW_COPY,
    ScreenSurfaceCommandCatalog,
    ScreenSurfaceWorkflow,
    ScreenSurfaceWorkflowPorts,
    normalize_standard_conversation_surface_command,
    strip_available_models_heading,
)

_CODING_MODEL_SELECTOR_PROFILE = SessionModelSelectorSurfaceProfile(
    subtitle="Access legacy models by running loushang --model <provider/model>.",
    footer="  Press number or enter to confirm or esc to go back",
    presentation="bottom-exclusive",
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
        self._command_catalog_override = command_catalog
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
                command_catalog=self.command_catalog,
                normalize_command=normalize_standard_conversation_surface_command,
                format_models=self._format_models,
                models_info_body=strip_available_models_heading,
                format_commands=self._format_commands,
                build_model_selector=self._build_model_selector,
                build_command_selector=self._build_command_selector,
                build_settings_content=self._build_settings_content,
                terminal_diagnostics=self._terminal_diagnostics,
                hotkeys=format_hotkeys,
                decide_approval=self._decide_approval,
            ),
            copy=STANDARD_SCREEN_SURFACE_WORKFLOW_COPY,
        )

    @property
    def coding_app(self) -> ScreenCodingTuiApp:
        app = self.app
        if not isinstance(app, ScreenCodingTuiApp):  # pragma: no cover - constructor
            raise TypeError("Coding surface manager requires ScreenCodingTuiApp")
        return app

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
        catalog = await self._presentation_command_catalog()
        return format_commands(catalog.commands(), query=query)

    async def _build_command_selector(self) -> ScreenSurfaceView:
        catalog = await self._presentation_command_catalog()
        return command_catalog_surface_view(catalog)

    async def _presentation_command_catalog(self) -> ScreenSurfaceCommandCatalog:
        if self._command_catalog_override is not None:
            return self._command_catalog_override
        return await snapshot_coding_command_catalog(self.session)

    async def _build_model_selector(self) -> ScreenSurfaceView:
        return await build_session_model_selector_surface(
            self.session,
            profile=_CODING_MODEL_SELECTOR_PROFILE,
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
        label = (await get_session_model_identity(self.session)).label
        if label is not None:
            self.coding_app.state.model_label = label


def _session_commands_provider(session: Any) -> Callable[[], Any] | None:
    getter = getattr(session, "list_commands", None)
    if not callable(getter):
        return None
    return getter


__all__ = ["ScreenSurfaceManager"]
