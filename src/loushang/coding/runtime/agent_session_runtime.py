from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from loushang.coding.session import AgentSession
from loushang.coding.session_manager import SessionManager
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.extensions.context import SessionShutdownEvent
from loushang.harness.runtime import copy_file_exclusive
from loushang.harness.session import (
    MissingSessionCwdError as HarnessMissingSessionCwdError,
)
from loushang.harness.session import (
    ProductSessionRuntime,
    SessionDiagnosticScope,
    SessionDiagnosticsRuntime,
    build_agent_product_session_runtime_ports,
    prepare_current_agent_session,
    session_file_from_session,
    session_id_from_session,
)

SessionFactory = Callable[..., AgentSession]
_copy_import_file = copy_file_exclusive


@dataclass(frozen=True)
class MissingSessionCwdIssue:
    session_cwd: str
    session_file: Path | None = None
    fallback_cwd: str | None = None


class MissingSessionCwdError(RuntimeError):
    def __init__(self, issue: MissingSessionCwdIssue) -> None:
        message = f"Session cwd is not available: {issue.session_cwd}"
        if issue.session_file is not None:
            message = f"{message} ({issue.session_file})"
        if issue.fallback_cwd is not None:
            message = f"{message}. Fallback cwd: {issue.fallback_cwd}"
        super().__init__(message)
        self.issue = issue


def get_missing_session_cwd_issue(
    session_manager: SessionManager,
    fallback_cwd: str | Path | None = None,
) -> MissingSessionCwdIssue | None:
    session_cwd = session_manager.get_cwd()
    candidate = Path(session_cwd).expanduser()
    if candidate.exists() and candidate.is_dir():
        return None
    return MissingSessionCwdIssue(
        session_cwd=session_cwd,
        session_file=session_manager.get_session_file(),
        fallback_cwd=str(fallback_cwd) if fallback_cwd is not None else None,
    )


class AgentSessionRuntime(
    ProductSessionRuntime[AgentSession, SessionManager, str],
):
    def __init__(
        self,
        *,
        session_dir: Path,
        session_factory: SessionFactory,
        persist: bool = True,
        current_session: AgentSession | None = None,
        diagnostics_service: DiagnosticsService | None = None,
        auto_refresh_session_index: bool = False,
        session_index_refresh_interval: float = 0.5,
        session_index_flush_delay: float = 0.25,
    ) -> None:
        self._diagnostics_service = diagnostics_service
        super().__init__(
            session_dir=session_dir,
            ports=build_agent_product_session_runtime_ports(
                runtime_host=self,
                transcript_session_type=SessionManager,
                session_dir=session_dir,
                session_factory=session_factory,
                persist=persist,
                copy_file=lambda source, destination: _copy_import_file(
                    source, destination
                ),
                diagnostics_runtime=self._session_diagnostics_runtime,
                record_shutdown_failure=self._record_shutdown_failure,
                translate_missing_cwd_error=_coding_missing_cwd_error,
            ),
            current_session=current_session,
            auto_refresh_session_index=auto_refresh_session_index,
            session_index_refresh_interval=session_index_refresh_interval,
            session_index_flush_delay=session_index_flush_delay,
        )
        if current_session is not None:
            prepare_current_agent_session(current_session, self)

    def _session_diagnostics_runtime(
        self,
        session: AgentSession | None = None,
    ) -> SessionDiagnosticsRuntime:
        active_session = session or self.current_session
        diagnostics_service = self._diagnostics_service or getattr(
            active_session,
            "diagnostics_service",
            None,
        )
        session_id = session_id_from_session(active_session) or ""
        return SessionDiagnosticsRuntime(
            diagnostics_service=diagnostics_service,
            get_scope=lambda: SessionDiagnosticScope(session_id=session_id),
            get_extension_diagnostics=lambda: None,
        )

    def _record_shutdown_failure(
        self,
        session: object,
        event: SessionShutdownEvent,
        exc: Exception,
    ) -> None:
        typed_session = cast(AgentSession, session)
        self._record_failure_for_session(
            typed_session,
            code="session_shutdown_failed",
            exc=exc,
            details={
                "reason": event.reason,
                "session_file": session_file_from_session(typed_session),
                "target_session_file": event.target_session_file,
            },
        )


def _coding_missing_cwd_error(
    error: HarnessMissingSessionCwdError,
) -> MissingSessionCwdError:
    session_ref = error.issue.session_ref
    return MissingSessionCwdError(
        MissingSessionCwdIssue(
            session_cwd=error.issue.session_cwd,
            session_file=Path(session_ref) if session_ref is not None else None,
            fallback_cwd=error.issue.fallback_cwd,
        )
    )
