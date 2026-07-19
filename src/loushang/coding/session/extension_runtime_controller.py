from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from loushang.harness.extensions.context import SessionRefreshEvent, SessionStartEvent
from loushang.harness.extensions.lifecycle import (
    ExtensionRuntimeCoordinator,
    ExtensionRuntimeOperation,
)
from loushang.harness.resources.diagnostics import ResourceDiagnostic

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
    _coordinator: (
        ExtensionRuntimeCoordinator[object, SessionStartEvent, SessionRefreshEvent]
        | None
    ) = field(init=False, default=None)

    def __post_init__(self) -> None:
        runner = self.extension_runner
        if runner is None:
            return
        self._coordinator = ExtensionRuntimeCoordinator(
            build_bindings=self.build_bindings,
            bind_runtime=lambda bindings: getattr(runner, "bind_runtime")(bindings),
            refresh_runtime=lambda bindings: getattr(runner, "refresh_runtime")(
                bindings
            ),
            emit_session_start=lambda event: getattr(runner, "emit_session_start")(
                event
            ),
            emit_session_refresh=lambda event: getattr(runner, "emit_session_refresh")(
                event
            ),
            refresh_resources=self.refresh_resources,
            record_failure=self._record_failure,
            sync_diagnostics=lambda: self.sync_extension_diagnostics(phase="runtime"),
            invalidate_contexts_driver=lambda message: _invalidate_contexts(
                runner, message
            ),
        )

    @property
    def is_refreshing(self) -> bool:
        coordinator = self._coordinator
        return coordinator is not None and coordinator.is_refreshing

    async def bind(self, *, reason: str) -> None:
        coordinator = self._coordinator
        if coordinator is None:
            return
        await coordinator.bind(
            self._start_event_for_reason(reason),
            reload=reason == "reload",
            stale_context_message=(
                "Extension context is stale after extension reload."
            ),
        )

    def bind_bindings(self) -> None:
        if self._coordinator is not None:
            self._coordinator.bind_bindings()

    async def refresh(self, *, reason: str) -> None:
        if self._coordinator is not None:
            await self._coordinator.refresh(SessionRefreshEvent(reason=reason))

    def refresh_bindings(self) -> None:
        if self._coordinator is not None:
            self._coordinator.refresh_bindings()

    def invalidate_contexts(self, message: str) -> None:
        if self._coordinator is not None:
            self._coordinator.invalidate_contexts(message)

    def _record_failure(
        self,
        operation: ExtensionRuntimeOperation,
        error: Exception,
    ) -> None:
        code, prefix = _FAILURE_DIAGNOSTICS[operation]
        self.record_runtime_diagnostic(
            ResourceDiagnostic(code=code, message=f"{prefix}: {error}")
        )

    def _start_event_for_reason(self, reason: str) -> SessionStartEvent:
        if self.session_start_event.reason == reason:
            return self.session_start_event
        return SessionStartEvent(reason=reason)


_FAILURE_DIAGNOSTICS: dict[ExtensionRuntimeOperation, tuple[str, str]] = {
    "resource_refresh": (
        "extension_resource_refresh_failed",
        "Extension resource refresh failed",
    ),
    "runtime_bind": (
        "extension_runtime_bind_failed",
        "Extension runtime bind failed",
    ),
    "runtime_refresh": (
        "extension_runtime_refresh_failed",
        "Extension runtime refresh failed",
    ),
    "session_start": (
        "extension_session_start_failed",
        "Extension hook 'session_start' failed",
    ),
    "session_refresh": (
        "extension_session_refresh_failed",
        "Extension hook 'session_refresh' failed",
    ),
}


def _invalidate_contexts(runner: object, message: str) -> None:
    invalidator = getattr(runner, "invalidate_contexts", None)
    if callable(invalidator):
        invalidator(message)
