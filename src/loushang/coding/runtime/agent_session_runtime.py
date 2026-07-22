from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from loushang.ai.types import TextPart, UserMessage
from loushang.coding.session import AgentSession
from loushang.coding.session_manager import SessionManager
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
)
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import (
    DiagnosticPhase,
)
from loushang.harness.extensions.context import (
    SessionBeforeForkEvent,
    SessionBeforeSwitchEvent,
    SessionShutdownEvent,
    SessionStartEvent,
)
from loushang.harness.runtime import (
    SessionOperationFailure,
    SessionOperationPhase,
    SessionOperationResult,
    copy_file_exclusive,
)
from loushang.harness.session import (
    ForkProfile,
    ForkSelection,
    ProductSessionRuntime,
    ProductSessionRuntimePorts,
    SessionCwdIssue,
    SessionDiagnosticScope,
    SessionDiagnosticsRuntime,
    SessionLifecycleDecision,
    SessionLifecycleHooks,
    SessionLifecycleTransition,
    dispose_session_only,
    emit_session_shutdown,
    invoke_session_factory,
    require_session_operation_session,
    resolve_existing_cwd,
    resolve_fork_target,
    session_file_from_session,
    session_id_from_session,
    session_manager_ref,
)
from loushang.harness.session import (
    MissingSessionCwdError as HarnessMissingSessionCwdError,
)

SessionFactory = Callable[..., AgentSession]
_copy_import_file = copy_file_exclusive
_CODING_FORK_PROFILE = ForkProfile(
    default_position="before",
    supported_positions=frozenset({"at", "before"}),
)


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
            ports=ProductSessionRuntimePorts(
                session_factory=session_factory,
                persist=persist,
                create_transcript=self._create_transcript_session,
                restore_transcript=self._restore_transcript_session,
                fork_transcript=self._fork_transcript_session,
                dispose_transcript=_dispose_transcript_session,
                transcript_for_session=lambda session: session.session_manager,
                transcript_cwd=lambda manager: manager.get_cwd(),
                transcript_session_ref=session_manager_ref,
                transcript_leaf_entry_id=lambda manager: manager.get_leaf_id(),
                build_session=lambda manager, current, transition: (
                    self._create_session_for_transition(
                        manager,
                        current=current,
                        transition=transition,
                    )
                ),
                validate_restored_transcript=self._validate_restored_transcript,
                fork_profile=_CODING_FORK_PROFILE,
                fork_target_resolver=_resolve_coding_fork_target,
                copy_file=lambda source, destination: _copy_import_file(
                    source, destination
                ),
                hooks=SessionLifecycleHooks(
                    before_transition=self._before_lifecycle_transition,
                    prepare_session=self._prepare_lifecycle_session,
                    activate_session=self._activate_lifecycle_session,
                    before_release=self._before_lifecycle_release,
                    dispose_session=dispose_session_only,
                    after_commit=self._after_lifecycle_commit,
                    on_failure=self._on_lifecycle_failure,
                ),
                diagnostics_runtime=self._session_diagnostics_runtime,
                record_index_refresh_failure=lambda exc, all_sessions: (
                    self._record_session_index_flush_failure(
                        exc,
                        all_sessions=all_sessions,
                    )
                ),
                rename_transcript=lambda path, name: SessionManager.rename_session(
                    path, name
                ),
                delete_transcript=lambda path, current_file: SessionManager.delete_session(
                    path,
                    current_session_file=current_file,
                ),
                current_session_file=session_file_from_session,
                record_operation_failure=lambda code, exc, details: (
                    self._record_session_operation_failure(
                        code=code,
                        exc=exc,
                        details=details,
                    )
                ),
                record_replacement_callback_failure=(
                    self._record_replacement_callback_failure
                ),
                resolve_import_cwd=resolve_existing_cwd,
                translate_missing_cwd_error=_coding_missing_cwd_error,
            ),
            current_session=current_session,
            auto_refresh_session_index=auto_refresh_session_index,
            session_index_refresh_interval=session_index_refresh_interval,
            session_index_flush_delay=session_index_flush_delay,
        )
        if current_session is not None:
            self._open_session_approvals(current_session)
            self._bind_runtime_host(current_session)

    async def _before_lifecycle_transition(
        self,
        current: AgentSession | None,
        transition: SessionLifecycleTransition,
    ) -> SessionLifecycleDecision | None:
        if (
            current is None
            or transition.metadata.get("emit_before_transition", True) is False
        ):
            return None
        runner = self._get_extension_runner(current)
        if runner is None:
            return None
        if transition.reason == "fork":
            entry_id = transition.fork_entry_id
            position = transition.fork_position
            if entry_id is None or position is None:
                raise ValueError("Fork transitions require entry_id and position")
            decision = await runner.before_session_fork(
                SessionBeforeForkEvent(
                    entry_id=entry_id,
                    cwd=current.session_manager.get_cwd(),
                    position=position,
                )
            )
        else:
            decision = await runner.before_session_switch(
                SessionBeforeSwitchEvent(
                    reason=transition.reason,
                    cwd=transition.cwd or current.session_manager.get_cwd(),
                    target_session_file=transition.target_session_ref,
                )
            )
        self._sync_session_extension_diagnostics(current)
        return SessionLifecycleDecision(
            cancelled=decision is not None and decision.cancel
        )

    def _prepare_lifecycle_session(
        self,
        session: AgentSession,
        _previous: AgentSession | None,
        _transition: SessionLifecycleTransition,
    ) -> None:
        self._prepare_session_for_replacement(session)

    async def _activate_lifecycle_session(
        self,
        session: AgentSession,
        previous: AgentSession | None,
        transition: SessionLifecycleTransition,
    ) -> None:
        self._open_session_approvals(session)
        if transition.metadata.get("activate_extensions", True) is False:
            return
        starter = getattr(session, "start_extension_runtime", None)
        if callable(starter):
            start_reason = (
                "startup"
                if previous is None and transition.reason == "new"
                else transition.reason
            )
            await starter(reason=start_reason)

    async def _before_lifecycle_release(
        self,
        session: AgentSession,
        target_session: AgentSession | None,
        transition: SessionLifecycleTransition,
    ) -> None:
        await self._prepare_session_shutdown(
            session,
            SessionShutdownEvent(
                reason=transition.reason,
                target_session_file=session_file_from_session(target_session),
            ),
        )

    async def _after_lifecycle_commit(
        self,
        result: SessionOperationResult[AgentSession, str | None],
        transition: SessionLifecycleTransition,
    ) -> None:
        session = require_session_operation_session(result)
        if (
            self.auto_refresh_session_index
            and transition.metadata.get("schedule_index", True) is not False
        ):
            self.request_session_index_refresh()
        options = transition.metadata.get("options")
        if isinstance(options, dict):
            await self._run_replacement_callbacks(
                session,
                options,
                include_setup=transition.metadata.get("include_setup") is True,
            )

    def _on_lifecycle_failure(
        self,
        failure: SessionOperationFailure[AgentSession],
        transition: SessionLifecycleTransition,
    ) -> None:
        if failure.phase is SessionOperationPhase.AFTER_COMMIT:
            return
        operation = transition.metadata.get("operation")
        if operation == "restore_session":
            self._record_session_operation_failure(
                code="session_restore_failed",
                exc=failure.error,
                details={
                    "operation": operation,
                    "session_ref": transition.metadata.get("session_ref"),
                    "target_session_file": transition.target_session_ref,
                    "fallback_cwd": transition.metadata.get("fallback_cwd"),
                    "missing_cwd": transition.metadata.get("missing_cwd"),
                },
            )
        elif operation == "import_from_jsonl":
            self._record_session_operation_failure(
                code="session_import_failed",
                exc=failure.error,
                details={
                    "operation": operation,
                    "input_path": transition.metadata.get("input_path"),
                    "source_path": transition.metadata.get("source_path"),
                    "target_session_file": transition.target_session_ref,
                    "cwd_override": transition.metadata.get("cwd_override"),
                },
            )

    def _create_session_for_transition(
        self,
        manager: SessionManager,
        *,
        current: AgentSession | None,
        transition: SessionLifecycleTransition,
    ) -> AgentSession:
        start_reason = (
            "startup"
            if current is None and transition.reason == "new"
            else transition.reason
        )
        return self._create_session(
            manager,
            SessionStartEvent(
                reason=start_reason,
                previous_session_file=session_file_from_session(current),
            ),
        )

    async def _create_transcript_session(
        self,
        cwd: str,
        parent_session_ref: str | None,
    ) -> SessionManager:
        return await SessionManager.new(
            session_dir=self.session_dir,
            cwd=cwd,
            persist=self.persist,
            parent_session=parent_session_ref,
        )

    async def _restore_transcript_session(
        self,
        session_ref: str | Path,
        cwd_override: str | None,
    ) -> SessionManager:
        return await SessionManager.open(
            self.resolve_session_file(session_ref),
            session_dir=self.session_dir,
            cwd_override=(
                resolve_existing_cwd(cwd_override)
                if cwd_override is not None
                else None
            ),
            persist=self.persist,
        )

    async def _fork_transcript_session(
        self,
        manager: SessionManager,
        target_entry_id: str | None,
    ) -> SessionManager:
        if target_entry_id is not None:
            return await manager.fork(target_entry_id)
        return await self._create_transcript_session(
            manager.get_cwd(),
            session_manager_ref(manager),
        )

    @staticmethod
    def _validate_restored_transcript(manager: SessionManager) -> None:
        missing_issue = get_missing_session_cwd_issue(manager)
        if missing_issue is None:
            return
        raise HarnessMissingSessionCwdError(
            SessionCwdIssue(
                session_cwd=missing_issue.session_cwd,
                session_ref=(
                    str(missing_issue.session_file)
                    if missing_issue.session_file is not None
                    else None
                ),
            )
        )

    async def _prepare_session_shutdown(
        self, session: AgentSession, event: SessionShutdownEvent
    ) -> None:
        try:
            await emit_session_shutdown(session, event)
        except Exception as exc:
            self._record_session_shutdown_failure(session=session, event=event, exc=exc)
        finally:
            self._sync_session_extension_diagnostics(session)

    def _create_session(
        self, manager: SessionManager, start_event: SessionStartEvent
    ) -> AgentSession:
        return invoke_session_factory(
            self.session_factory,
            manager,
            session_start_event=start_event,
        )

    def _bind_runtime_host(self, session: AgentSession) -> None:
        setter = getattr(session, "set_extension_runtime_host", None)
        if callable(setter):
            setter(self)

    def _prepare_session_for_replacement(self, session: AgentSession) -> None:
        stage_session_approvals = getattr(session, "_stage_session_approvals", None)
        if callable(stage_session_approvals):
            stage_session_approvals()
        self._bind_runtime_host(session)

    @staticmethod
    def _open_session_approvals(session: AgentSession) -> None:
        open_session_approvals = getattr(session, "_open_session_approvals", None)
        if callable(open_session_approvals):
            open_session_approvals()

    def _record_session_index_flush_failure(
        self, exc: Exception, *, all_sessions: bool
    ) -> None:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self.current_session
            diagnostics_service = (
                current_session.diagnostics_service
                if current_session is not None
                else None
            )
        if diagnostics_service is None:
            return
        diagnostics_service.capture_failure(
            code="session_index_refresh_failed",
            error=exc,
            phase="runtime",
            source="session",
            session_id=getattr(self.current_session, "session_id", None),
            details={
                "all_sessions": all_sessions,
                "session_dir": str(self.session_dir),
            },
        )

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

    def _record_session_operation_failure(
        self,
        *,
        code: str,
        exc: Exception,
        details: dict[str, object],
    ) -> None:
        diagnostics_service = self._diagnostics_service
        current_session = self.current_session
        if diagnostics_service is None and current_session is not None:
            diagnostics_service = current_session.diagnostics_service
        if diagnostics_service is None:
            return
        diagnostics_service.capture_failure(
            code=code,
            error=exc,
            phase="runtime",
            source="session",
            session_id=getattr(current_session, "session_id", None),
            details=details,
        )

    def _record_session_shutdown_failure(
        self,
        *,
        session: AgentSession,
        event: SessionShutdownEvent,
        exc: Exception,
    ) -> None:
        diagnostics_service = self._diagnostics_service or getattr(
            session, "diagnostics_service", None
        )
        if diagnostics_service is None:
            return
        diagnostics_service.capture_failure(
            code="session_shutdown_failed",
            error=exc,
            phase="runtime",
            source="session",
            session_id=session_id_from_session(session),
            details={
                "reason": event.reason,
                "session_file": session_file_from_session(session),
                "target_session_file": event.target_session_file,
            },
        )

    def _record_replacement_callback_failure(
        self,
        *,
        session: AgentSession,
        callback_name: str,
        exc: Exception,
    ) -> None:
        diagnostics_service = self._diagnostics_service or getattr(
            session, "diagnostics_service", None
        )
        if diagnostics_service is None:
            return
        diagnostics_service.capture_failure(
            code="session_replacement_callback_failed",
            error=exc,
            phase="runtime",
            source="session",
            session_id=session_id_from_session(session),
            details={"callback": callback_name},
        )

    def _sync_session_extension_diagnostics(
        self,
        session: AgentSession,
        *,
        phase: DiagnosticPhase = "runtime",
    ) -> None:
        sync = getattr(session, "_sync_extension_diagnostics", None)
        if callable(sync):
            sync(phase=phase)
            return

        diagnostics_service = self._diagnostics_service or getattr(
            session, "diagnostics_service", None
        )
        if diagnostics_service is None:
            return
        runner = self._get_extension_runner(session)
        get_diagnostics = (
            getattr(runner, "get_diagnostics", None) if runner is not None else None
        )
        if not callable(get_diagnostics):
            return
        diagnostics = get_diagnostics()
        recorded_attr = "_runtime_synced_extension_diagnostics_count"
        recorded = getattr(session, recorded_attr, 0)
        if not isinstance(recorded, int) or recorded < 0:
            recorded = 0
        if recorded >= len(diagnostics):
            return
        diagnostics_service.record_many(
            diagnostics_service.normalize_resource_diagnostic(
                diagnostic,
                phase=phase,
                source="extensions",
                session_id=session_id_from_session(session),
            )
            for diagnostic in diagnostics[recorded:]
        )
        try:
            setattr(session, recorded_attr, len(diagnostics))
        except Exception:
            return

    def _get_extension_runner(self, session: AgentSession):
        return getattr(
            session, "extension_runner", getattr(session, "_extension_runner", None)
        )


def _resolve_fork_target(
    manager: SessionManager, entry_id: str, *, position: str
) -> tuple[str | None, str | None]:
    selection = resolve_fork_target(
        manager,
        entry_id,
        position=position,
        get_entry=lambda current, target: current.get_entry(target),
        is_before_target=lambda entry: (
            entry.kind == AGENT_MESSAGE_KIND
            and isinstance(entry.payload, UserMessage)
        ),
        get_parent_id=lambda entry: entry.parent_id,
        project_payload=lambda entry: _user_message_text(entry.payload),
        invalid_before_message="Fork position 'before' requires a user message entry.",
    )
    return selection.target_entry_id, selection.payload


def _resolve_coding_fork_target(
    session: AgentSession,
    entry_id: str,
    position: str,
) -> ForkSelection[str]:
    target_entry_id, selected_text = _resolve_fork_target(
        session.session_manager,
        entry_id,
        position=position,
    )
    return ForkSelection(target_entry_id=target_entry_id, payload=selected_text)


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


async def _dispose_transcript_session(manager: SessionManager) -> None:
    await manager.dispose_runtime_profile()


def _user_message_text(message: UserMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.text for part in content if isinstance(part, TextPart))
    return ""
