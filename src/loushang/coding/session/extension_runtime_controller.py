from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass

from loushang.coding.extensions import SessionRefreshEvent, SessionStartEvent
from loushang.coding.loader import ResourceDiagnostic

BuildBindings = Callable[[], object]
RefreshResources = Callable[[], object | None]
RecordRuntimeDiagnostic = Callable[[ResourceDiagnostic], None]
SyncExtensionDiagnostics = Callable[..., None]


@dataclass
class ExtensionRuntimeController:
    extension_runner: object | None
    build_bindings: BuildBindings
    session_start_event: SessionStartEvent
    refresh_resources: RefreshResources
    record_runtime_diagnostic: RecordRuntimeDiagnostic
    sync_extension_diagnostics: SyncExtensionDiagnostics
    _refreshing: bool = False

    @property
    def is_refreshing(self) -> bool:
        return self._refreshing

    async def bind(self, *, reason: str) -> None:
        if self.extension_runner is None:
            return
        if reason == "reload":
            self.invalidate_contexts("Extension context is stale after extension reload.")
            try:
                refreshed = self.refresh_resources()
                if inspect.isawaitable(refreshed):
                    await refreshed
            except Exception as exc:
                self.record_runtime_diagnostic(
                    ResourceDiagnostic(
                        code="extension_resource_refresh_failed",
                        message=f"Extension resource refresh failed: {exc}",
                    )
                )
                return
        try:
            self.extension_runner.bind_runtime(self.build_bindings())
        except Exception as exc:
            self.record_runtime_diagnostic(
                ResourceDiagnostic(
                    code="extension_runtime_bind_failed",
                    message=f"Extension runtime bind failed: {exc}",
                )
            )
            return
        try:
            await self.extension_runner.emit_session_start(self._start_event_for_reason(reason))
        except Exception as exc:
            self.record_runtime_diagnostic(
                ResourceDiagnostic(
                    code="extension_session_start_failed",
                    message=f"Extension hook 'session_start' failed: {exc}",
                )
            )
        self.sync_extension_diagnostics(phase="runtime")

    def bind_bindings(self) -> None:
        if self.extension_runner is None:
            return
        try:
            self.extension_runner.bind_runtime(self.build_bindings())
        except Exception as exc:
            self.record_runtime_diagnostic(
                ResourceDiagnostic(
                    code="extension_runtime_bind_failed",
                    message=f"Extension runtime bind failed: {exc}",
                )
            )

    async def refresh(self, *, reason: str) -> None:
        if self.extension_runner is None:
            return
        try:
            self.extension_runner.refresh_runtime(self.build_bindings())
        except Exception as exc:
            self.record_runtime_diagnostic(
                ResourceDiagnostic(
                    code="extension_runtime_refresh_failed",
                    message=f"Extension runtime refresh failed: {exc}",
                )
            )
            return
        self._refreshing = True
        try:
            await self.extension_runner.emit_session_refresh(SessionRefreshEvent(reason=reason))
        except Exception as exc:
            self.record_runtime_diagnostic(
                ResourceDiagnostic(
                    code="extension_session_refresh_failed",
                    message=f"Extension hook 'session_refresh' failed: {exc}",
                )
            )
        finally:
            self._refreshing = False
        self.sync_extension_diagnostics(phase="runtime")

    def refresh_bindings(self) -> None:
        if self.extension_runner is None:
            return
        try:
            self.extension_runner.refresh_runtime(self.build_bindings())
        except Exception as exc:
            self.record_runtime_diagnostic(
                ResourceDiagnostic(
                    code="extension_runtime_refresh_failed",
                    message=f"Extension runtime refresh failed: {exc}",
                )
            )

    def invalidate_contexts(self, message: str) -> None:
        if self.extension_runner is None:
            return
        invalidator = getattr(self.extension_runner, "invalidate_contexts", None)
        if callable(invalidator):
            invalidator(message)

    def _start_event_for_reason(self, reason: str) -> SessionStartEvent:
        if self.session_start_event.reason == reason:
            return self.session_start_event
        return SessionStartEvent(reason=reason)
