from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from loushang.coding.continuity import bind_coding_continuity
from loushang.coding.model_selection_tui import select_available_model
from loushang.coding.ui.hotkeys import format_hotkeys
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.settings_page import build_coding_settings_page
from loushang.harness.continuity import ContinuityTarget
from loushang.harnesstui.continuity import build_continuity_surface_view
from loushang.harnesstui.conversation.agent_application import (
    build_agent_screen_surface_workflow_ports,
    current_agent_runtime_session,
)
from loushang.harnesstui.conversation.fork import (
    ForkPromptCandidate,
    build_fork_prompt_surface_view,
)
from loushang.harnesstui.conversation.rename import (
    build_session_rename_surface_view,
)
from loushang.harnesstui.conversation.side_question import (
    build_side_question_surface_view,
)
from loushang.harnesstui.selection.binding import (
    SessionModelSelectorSurfaceProfile,
)
from loushang.harnesstui.status.provider import StatusProvider
from loushang.harnesstui.surface.workflow import (
    STANDARD_SCREEN_SURFACE_WORKFLOW_COPY,
    ScreenSurfaceCommandCatalog,
    ScreenSurfaceForkResult,
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
        runtime: Any | None = None,
        status_provider: StatusProvider,
        on_approval: Callable[[dict[str, Any]], Awaitable[bool | None]] | None = None,
        command_catalog: ScreenSurfaceCommandCatalog | None = None,
    ) -> None:
        self.session = session
        self.runtime = runtime
        self.status_provider = status_provider
        self.continuity = (
            bind_coding_continuity(runtime) if runtime is not None else None
        )
        ports = build_agent_screen_surface_workflow_ports(
            session,
            session_provider=self._current_session,
            select_model=lambda value: select_available_model(
                self._current_session(),
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
            build_resume_surface=(
                self._build_resume_surface if runtime is not None else None
            ),
            activate_continuity=(
                self._activate_continuity if runtime is not None else None
            ),
            build_delete_surface=(
                self._build_delete_surface if runtime is not None else None
            ),
            delete_continuity=(
                self._delete_continuity if runtime is not None else None
            ),
            build_fork_surface=(
                self._build_fork_surface if runtime is not None else None
            ),
            fork_session=(
                self._fork_session if runtime is not None else None
            ),
            build_rename_surface=self._build_rename_surface,
            rename_session=self._rename_session,
            build_side_question_surface=self._build_side_question_surface,
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

    def _current_session(self) -> object:
        if self.runtime is None:
            return self.session
        return current_agent_runtime_session(self.runtime, self.session)

    def _build_resume_surface(self):
        if self.continuity is None:
            raise RuntimeError("Session runtime is not available")
        session = self._current_session()
        settings_manager = getattr(session, "settings_manager", None)
        keybindings = getattr(settings_manager, "get_keybindings", None)
        return build_continuity_surface_view(
            hub=self.continuity.hub,
            request_render=self.coding_app.request_render,
            keybindings=keybindings() if callable(keybindings) else None,
        )

    async def _activate_continuity(self, target: object) -> str:
        if self.continuity is None:
            raise RuntimeError("Session runtime is not available")
        if not isinstance(target, ContinuityTarget):
            raise TypeError("Resume requires a provider-qualified continuity target")
        lease = await self.continuity.hub.prepare(target)
        try:
            result = await lease.consume()
        except BaseException:
            await lease.abort()
            raise
        await lease.close()
        if getattr(result, "cancelled", False):
            raise RuntimeError("Session resume was cancelled")
        return f"Resumed session {target.opaque_id}"

    def _build_delete_surface(self):
        if self.continuity is None:
            raise RuntimeError("Session runtime is not available")
        current = self._current_session()
        current_id = getattr(current, "session_id", None)
        return build_continuity_surface_view(
            hub=self.continuity.hub,
            request_render=self.coding_app.request_render,
            include_summary=lambda summary: summary.target.opaque_id != current_id,
            title="Delete a previous session",
            selection_action="delete",
            purpose="delete",
        )

    async def _delete_continuity(self, target: object) -> str:
        if self.continuity is None:
            raise RuntimeError("Session runtime is not available")
        if not isinstance(target, ContinuityTarget):
            raise TypeError("Delete requires a provider-qualified continuity target")
        deleted = await self.continuity.hub.delete(target)
        if not deleted:
            raise RuntimeError("The selected session was already deleted")
        return f"Deleted session {target.opaque_id}"

    def _build_fork_surface(self):
        session = self._current_session()
        getter = getattr(session, "get_user_messages_for_forking", None)
        if not callable(getter):
            raise RuntimeError("Prompt history is not available for this session")
        candidates: list[ForkPromptCandidate] = []
        for value in getter():
            if not isinstance(value, Mapping):
                raise TypeError("Fork prompt candidates must be mappings")
            entry_id = value.get("entry_id")
            text = value.get("text")
            if not isinstance(entry_id, str) or not entry_id.strip():
                raise TypeError("Fork prompt candidates require an entry_id")
            if not isinstance(text, str) or not text.strip():
                continue
            candidates.append(
                ForkPromptCandidate(entry_id=entry_id, text=text)
            )
        return build_fork_prompt_surface_view(
            candidates=candidates,
            request_render=lambda: self.coding_app.request_render("product"),
        )

    async def _fork_session(self, target: object) -> ScreenSurfaceForkResult:
        if self.runtime is None:
            raise RuntimeError("Session runtime is not available")
        if not isinstance(target, str) or not target.strip():
            raise TypeError("Fork requires a selected prompt")
        operation = getattr(self.runtime, "fork_session_operation", None)
        if not callable(operation):
            raise RuntimeError("Session forking is not available")
        result = await operation(target, position="before")
        if getattr(result, "cancelled", False):
            raise RuntimeError("Session fork was cancelled")
        selected_text = getattr(result, "payload", None)
        if not isinstance(selected_text, str):
            raise RuntimeError("Forked session did not return the selected prompt")
        return ScreenSurfaceForkResult(
            status="Forked from selected prompt",
            composer_text=selected_text,
        )

    def _build_rename_surface(self):
        session = self._current_session()
        name = getattr(session, "session_name", None)
        return build_session_rename_surface_view(
            current_name=name if isinstance(name, str) else None
        )

    async def _rename_session(self, name: str | None) -> str:
        session = self._current_session()
        rename = getattr(session, "set_session_name", None)
        if not callable(rename):
            raise RuntimeError("Session renaming is not available")
        await rename(name)
        self.coding_app.state.session_label = (
            name or getattr(session, "session_id", None)
        )
        return f"Session renamed to {name}" if name else "Session name cleared"

    async def _build_settings_content(self) -> object:
        session = self._current_session()
        return await build_coding_settings_page(
            session=session,
            status_provider=self.status_provider,
            settings_manager=getattr(session, "settings_manager", None),
            statusline_preview=self.coding_app.statusline_preview_snapshot,
        )

    def _build_side_question_surface(self, question: str):
        session = self._current_session()
        ask = getattr(session, "ask_side_question", None)
        cancel = getattr(session, "cancel_side_question", None)
        if not callable(ask) or not callable(cancel):
            raise RuntimeError("Side questions are not available for this session.")
        return build_side_question_surface_view(
            question=question,
            ask=ask,
            cancel=cancel,
            request_render=lambda: self.coding_app.request_render("product"),
        )


__all__ = ["ScreenSurfaceManager"]
