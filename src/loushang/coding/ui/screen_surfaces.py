from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loushang.coding.model_selection_tui import select_available_model
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.settings_page import build_coding_settings_page
from loushang.harnesstui.conversation.agent_application import (
    build_agent_screen_surface_workflow_ports,
)
from loushang.harnesstui.selection.binding import (
    SessionModelSelectorSurfaceProfile,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.harnesstui.surface.workflow import (
    STANDARD_SCREEN_SURFACE_WORKFLOW_COPY,
    ScreenSurfaceCommandCatalog,
    ScreenSurfaceWorkflow,
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
        ports = build_agent_screen_surface_workflow_ports(
            session,
            select_model=lambda value: select_available_model(
                session,
                query=value,
            ),
            set_model_label=lambda label: setattr(
                app.state,
                "model_label",
                label,
            ),
            build_settings_content=self._build_settings_content,
            terminal_diagnostics=self._terminal_diagnostics,
            hotkeys=format_hotkeys,
            on_approval=on_approval,
            command_catalog=command_catalog,
            model_selector_profile=_CODING_MODEL_SELECTOR_PROFILE,
        )
        self.command_catalog = ports.command_catalog
        super().__init__(
            app=app,
            ports=ports,
            copy=STANDARD_SCREEN_SURFACE_WORKFLOW_COPY,
        )

    @property
    def coding_app(self) -> ScreenCodingTuiApp:
        app = self.app
        if not isinstance(app, ScreenCodingTuiApp):  # pragma: no cover - constructor
            raise TypeError("Coding surface manager requires ScreenCodingTuiApp")
        return app

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


__all__ = ["ScreenSurfaceManager"]
