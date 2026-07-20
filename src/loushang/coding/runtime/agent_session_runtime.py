from __future__ import annotations

import errno
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from loushang.ai.types import TextPart, UserMessage
from loushang.coding.session import AgentSession
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    AgentTranscriptDirectoryRuntime,
    SessionSummary,
)
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import (
    DiagnosticPhase,
    DiagnosticRecord,
    DiagnosticsQuery,
    DiagnosticSummary,
    ErrorReport,
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
    run_replacement_callbacks,
)
from loushang.harness.session import (
    ForkProfile,
    ForkSelection,
    SessionCwdIssue,
    SessionLifecycleDecision,
    SessionLifecycleHooks,
    SessionLifecycleRuntime,
    SessionLifecycleTransition,
)
from loushang.harness.session import (
    MissingSessionCwdError as HarnessMissingSessionCwdError,
)

_copy_import_file = copy_file_exclusive

SessionFactory = Callable[..., AgentSession]
SessionRebindCallback = Callable[[AgentSession], Awaitable[None]]
BeforeSessionInvalidateCallback = Callable[[], None]
_SessionOperationResult = SessionOperationResult[AgentSession, str | None]
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


class _CodingSessionLifecycleStore:
    """Bind the generic lifecycle transaction to Coding's transcript session."""

    def __init__(self, runtime: AgentSessionRuntime) -> None:
        self._runtime = runtime
        self._known_cwds: dict[int, str] = {}

    async def create(
        self,
        current_session: AgentSession | None,
        transition: SessionLifecycleTransition,
        *,
        cwd: str,
        parent_session_ref: str | None,
    ) -> AgentSession:
        manager = await SessionManager.new(
            session_dir=self._runtime.session_dir,
            cwd=cwd,
            persist=self._runtime.persist,
            parent_session=parent_session_ref,
        )
        return self._build_session(
            manager,
            current=current_session,
            transition=transition,
        )

    async def restore(
        self,
        current_session: AgentSession | None,
        transition: SessionLifecycleTransition,
        session_ref: str | Path,
        *,
        cwd_override: str | None = None,
    ) -> AgentSession:
        session_file = self._runtime._resolve_session_file(session_ref)
        manager = await SessionManager.open(
            session_file,
            session_dir=self._runtime.session_dir,
            cwd_override=(
                self._runtime._resolve_import_cwd(cwd_override)
                if cwd_override is not None
                else None
            ),
            persist=self._runtime.persist,
        )
        missing_issue = get_missing_session_cwd_issue(manager)
        if missing_issue is not None:
            await manager.dispose_runtime_profile()
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
        return self._build_session(
            manager,
            current=current_session,
            transition=transition,
        )

    async def fork(
        self,
        session: AgentSession,
        transition: SessionLifecycleTransition,
        target_entry_id: str | None,
    ) -> AgentSession:
        if target_entry_id is None:
            manager = await SessionManager.new(
                session_dir=self._runtime.session_dir,
                cwd=session.session_manager.get_cwd(),
                persist=self._runtime.persist,
                parent_session=_session_file_from_session(session),
            )
        else:
            manager = await session.session_manager.fork(target_entry_id)
        return self._build_session(
            manager,
            current=session,
            transition=transition,
        )

    def get_cwd(self, session: AgentSession) -> str:
        manager = getattr(session, "session_manager", None)
        getter = getattr(manager, "get_cwd", None)
        if callable(getter):
            return getter()
        return self._known_cwds[id(session)]

    def get_session_ref(self, session: AgentSession) -> str | None:
        return _session_file_from_session(session)

    def get_leaf_entry_id(self, session: AgentSession) -> str | None:
        return session.session_manager.get_leaf_id()

    def _build_session(
        self,
        manager: SessionManager,
        *,
        current: AgentSession | None,
        transition: SessionLifecycleTransition,
    ) -> AgentSession:
        session = self._runtime._create_session_for_transition(
            manager,
            current=current,
            transition=transition,
        )
        self._known_cwds[id(session)] = manager.get_cwd()
        return session


class AgentSessionRuntime(AgentTranscriptDirectoryRuntime):
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
            auto_refresh_session_index=auto_refresh_session_index,
            session_index_refresh_interval=session_index_refresh_interval,
            session_index_flush_delay=session_index_flush_delay,
            record_index_refresh_failure=lambda exc, all_sessions: (
                self._record_session_index_flush_failure(
                    exc,
                    all_sessions=all_sessions,
                )
            ),
        )
        self.session_factory = session_factory
        self._session_factory_accepts_start_event = _accepts_session_start_event(
            session_factory
        )
        self.persist = persist
        self._lifecycle = SessionLifecycleRuntime[AgentSession, str](
            store=_CodingSessionLifecycleStore(self),
            current_session=current_session,
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
                dispose_session=_dispose_session_only,
                after_commit=self._after_lifecycle_commit,
                on_failure=self._on_lifecycle_failure,
            ),
        )
        self._session_host = self._lifecycle.transition_host
        if current_session is not None:
            self._open_session_approvals(current_session)
            self._bind_runtime_host(current_session)

    @property
    def _current_session(self) -> AgentSession | None:
        return self._session_host.current

    @property
    def session(self) -> AgentSession:
        return self._require_current_session()

    @property
    def current_session(self) -> AgentSession | None:
        return self._current_session

    @property
    def cwd(self) -> str:
        return self._require_current_session().session_manager.get_cwd()

    def set_rebind_session(self, callback: SessionRebindCallback | None) -> None:
        self._session_host.set_rebind(callback)

    def set_before_session_invalidate(
        self, callback: BeforeSessionInvalidateCallback | None
    ) -> None:
        self._session_host.set_before_invalidate(callback)

    def subscribe_before_session_invalidate(
        self,
        callback: BeforeSessionInvalidateCallback,
    ) -> Callable[[], None]:
        return self._session_host.subscribe_before_invalidate(callback)

    def subscribe_after_session_invalidate(
        self,
        callback: BeforeSessionInvalidateCallback,
    ) -> Callable[[], None]:
        return self._session_host.subscribe_after_invalidate(callback)

    async def create_session(
        self, *, cwd: str, parent_session: str | None = None
    ) -> AgentSession:
        return await self.new_session(cwd=cwd, parent_session=parent_session)

    async def new_session(
        self, *, cwd: str | Path | None = None, parent_session: str | None = None
    ) -> AgentSession:
        result = await self.new_session_operation(
            cwd=cwd,
            parent_session=parent_session,
        )
        return _require_operation_session(result)

    async def new_session_operation(
        self,
        *,
        cwd: str | Path | None = None,
        parent_session: str | None = None,
        setup: object | None = None,
        with_session: object | None = None,
    ) -> _SessionOperationResult:
        """Create a session and run optional standard replacement callbacks."""
        options = _replacement_callback_options(
            setup=setup,
            with_session=with_session,
        )
        return await self._run_new_session_operation(
            cwd=cwd,
            parent_session=parent_session,
            options=options or None,
        )

    async def _run_new_session_operation(
        self,
        *,
        cwd: str | Path | None = None,
        parent_session: str | None = None,
        options: dict[str, object] | None = None,
    ) -> _SessionOperationResult:
        return await self._lifecycle.new(
            cwd=self._resolve_import_cwd(cwd) if cwd is not None else None,
            parent_session_ref=parent_session,
            metadata=self._lifecycle_metadata(
                operation="new_session",
                options=options,
                include_setup=True,
            ),
        )

    async def switch_session(self, session_id: str | Path) -> AgentSession:
        return await self.restore_session(session_id)

    async def restore_session(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: Literal["error", "fallback"] = "error",
    ) -> AgentSession:
        result = await self.restore_session_operation(
            session_id,
            fallback_cwd=fallback_cwd,
            missing_cwd=missing_cwd,
        )
        return _require_operation_session(result)

    async def restore_session_operation(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: Literal["error", "fallback"] = "error",
        with_session: object | None = None,
    ) -> _SessionOperationResult:
        """Restore a session and run an optional standard replacement callback."""
        options = _replacement_callback_options(with_session=with_session)
        return await self._run_restore_session_operation(
            session_id,
            fallback_cwd=fallback_cwd,
            missing_cwd=missing_cwd,
            options=options or None,
        )

    async def _run_restore_session_operation(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: Literal["error", "fallback"] = "error",
        options: dict[str, object] | None = None,
    ) -> _SessionOperationResult:
        session_file = self._resolve_session_file(session_id)
        try:
            return await self._lifecycle.restore(
                session_file,
                fallback_cwd=(str(fallback_cwd) if fallback_cwd is not None else None),
                missing_cwd=missing_cwd,
                metadata=self._lifecycle_metadata(
                    operation="restore_session",
                    options=options,
                    session_ref=str(session_id),
                    target_session_file=str(session_file),
                    fallback_cwd=(
                        str(fallback_cwd) if fallback_cwd is not None else None
                    ),
                    missing_cwd=missing_cwd,
                ),
            )
        except HarnessMissingSessionCwdError as exc:
            raise _coding_missing_cwd_error(exc) from exc

    async def fork_session(
        self, entry_id: str, *, position: str = "at"
    ) -> AgentSession:
        result = await self.fork_session_operation(entry_id, position=position)
        return _require_operation_session(result)

    async def fork_session_operation(
        self,
        entry_id: str | None,
        *,
        position: str = "at",
        with_session: object | None = None,
    ) -> _SessionOperationResult:
        """Fork the active transcript and run an optional replacement callback."""
        options = _replacement_callback_options(with_session=with_session)
        return await self._run_fork_session_operation(
            entry_id,
            position=position,
            options=options or None,
        )

    async def fork_session_with_result(
        self, entry_id: str, *, position: str = "at"
    ) -> tuple[AgentSession, str | None]:
        result = await self._run_fork_session_operation(entry_id, position=position)
        return _require_operation_session(result), result.payload

    async def _run_fork_session_operation(
        self,
        entry_id: str | None,
        *,
        position: str = "at",
        options: dict[str, object] | None = None,
    ) -> _SessionOperationResult:
        return await self._lifecycle.fork(
            entry_id,
            position=position,
            metadata=self._lifecycle_metadata(
                operation="fork_session",
                options=options,
            ),
        )

    async def fork(
        self, entry_id: str, options: object | None = None
    ) -> dict[str, object]:
        opts = options if isinstance(options, dict) else {}
        position = opts.get("position", "before")
        if position not in {"before", "at"}:
            raise ValueError(f"Unsupported fork position: {position}")
        operation = await self._run_fork_session_operation(
            entry_id,
            position=position,
            options=opts,
        )
        result: dict[str, object] = {"cancelled": operation.cancelled}
        if operation.payload is not None:
            result["selectedText"] = operation.payload
            result["selected_text"] = operation.payload
        return result

    async def clone_session(self) -> AgentSession:
        result = await self._run_fork_session_operation(None)
        return _require_operation_session(result)

    async def clone(self) -> dict[str, bool]:
        result = await self._run_fork_session_operation(None)
        return {"cancelled": result.cancelled}

    async def import_from_jsonl(
        self, input_path: str | Path, cwd_override: str | Path | None = None
    ) -> dict[str, bool]:
        result = await self._run_import_session_operation(input_path, cwd_override)
        return {"cancelled": result.cancelled}

    async def _run_import_session_operation(
        self, input_path: str | Path, cwd_override: str | Path | None = None
    ) -> _SessionOperationResult:
        source = Path(input_path).expanduser().resolve()
        try:
            return await self._lifecycle.import_file(
                source,
                destination_dir=self.session_dir,
                cwd_override=(str(cwd_override) if cwd_override is not None else None),
                metadata=self._lifecycle_metadata(
                    operation="import_from_jsonl",
                    input_path=str(input_path),
                    source_path=str(source),
                    cwd_override=(
                        str(cwd_override) if cwd_override is not None else None
                    ),
                ),
            )
        except HarnessMissingSessionCwdError as exc:
            raise _coding_missing_cwd_error(exc) from exc

    async def replace_current_session(self, session: AgentSession) -> None:
        await self._lifecycle.replace(
            session,
            metadata=self._lifecycle_metadata(
                operation="replace_current_session",
                activate_extensions=False,
                emit_before_transition=False,
                schedule_index=False,
            ),
        )

    def get_current_session(self) -> AgentSession | None:
        return self._current_session

    async def rename_session(
        self, session_id: str | Path, name: str | None
    ) -> SessionSummary:
        session_file: Path | None = None
        try:
            session_file = self._resolve_session_file(session_id)
            summary = await SessionManager.rename_session(session_file, name)
            if self.auto_refresh_session_index:
                self.request_session_index_refresh()
            return summary
        except Exception as exc:
            self._record_session_operation_failure(
                code="session_rename_failed",
                exc=exc,
                details={
                    "operation": "rename_session",
                    "session_ref": str(session_id),
                    "target_session_file": str(session_file)
                    if session_file is not None
                    else None,
                    "name": name,
                },
            )
            raise

    async def delete_session(self, session_id: str | Path) -> bool:
        session_file: Path | None = None
        try:
            session_file = self._resolve_session_file(session_id)
            deleted = await SessionManager.delete_session(
                session_file,
                current_session_file=_session_file_from_session(self._current_session),
            )
            if deleted and self.auto_refresh_session_index:
                self.request_session_index_refresh()
            return deleted
        except Exception as exc:
            self._record_session_operation_failure(
                code="session_delete_failed",
                exc=exc,
                details={
                    "operation": "delete_session",
                    "session_ref": str(session_id),
                    "target_session_file": str(session_file)
                    if session_file is not None
                    else None,
                },
            )
            raise

    def get_last_diagnostics(self, limit: int = 50) -> list[DiagnosticRecord]:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = (
                current_session.diagnostics_service
                if current_session is not None
                else None
            )
        if diagnostics_service is None:
            return []
        return diagnostics_service.get_last_diagnostics(limit=limit)

    def get_diagnostics(
        self, query: DiagnosticsQuery | None = None
    ) -> list[DiagnosticRecord]:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = (
                current_session.diagnostics_service
                if current_session is not None
                else None
            )
        if diagnostics_service is None:
            return []
        return diagnostics_service.get_diagnostics(query=query)

    def get_session_diagnostics(
        self, query: DiagnosticsQuery | None = None
    ) -> list[DiagnosticRecord]:
        current_session = self._require_current_session()
        getter = getattr(current_session, "get_session_diagnostics", None)
        if callable(getter):
            return getter(query)
        diagnostics_service = (
            self._diagnostics_service or current_session.diagnostics_service
        )
        if diagnostics_service is None:
            return []
        return diagnostics_service.get_diagnostics(
            query=_diagnostics_query_for_session(query, current_session.session_id)
        )

    def get_diagnostics_summary(
        self, query: DiagnosticsQuery | None = None
    ) -> DiagnosticSummary:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = (
                current_session.diagnostics_service
                if current_session is not None
                else None
            )
        if diagnostics_service is None:
            return DiagnosticsService().get_diagnostics_summary(query=query)
        return diagnostics_service.get_diagnostics_summary(query=query)

    def get_session_diagnostics_summary(
        self, query: DiagnosticsQuery | None = None
    ) -> DiagnosticSummary:
        current_session = self._require_current_session()
        diagnostics_service = (
            self._diagnostics_service or current_session.diagnostics_service
        )
        if diagnostics_service is None:
            return DiagnosticsService().get_diagnostics_summary(query=query)
        return diagnostics_service.get_diagnostics_summary(
            query=_diagnostics_query_for_session(query, current_session.session_id)
        )

    def get_last_error_report(self) -> ErrorReport | None:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = (
                current_session.diagnostics_service
                if current_session is not None
                else None
            )
        if diagnostics_service is None:
            return None
        return diagnostics_service.get_last_error_report()

    def get_packages(
        self, *, catalog_path: str | None = None
    ) -> list[dict[str, object]]:
        current_session = self._require_current_session()
        getter = getattr(current_session, "get_packages", None)
        if not callable(getter):
            return []
        return getter(catalog_path=catalog_path)

    async def materialize_package(self, source: str) -> dict[str, object]:
        current_session = self._require_current_session()
        materialize = getattr(current_session, "materialize_package", None)
        if not callable(materialize):
            raise RuntimeError("Package materializer is not available.")
        result = materialize(source)
        if inspect.isawaitable(result):
            return await result
        return result

    async def install_package(
        self, source: str, *, scope: str = "project"
    ) -> dict[str, object]:
        current_session = self._require_current_session()
        install = getattr(current_session, "install_package", None)
        if not callable(install):
            raise RuntimeError("Package installation is not available.")
        result = install(source, scope=scope)
        if inspect.isawaitable(result):
            return await result
        return result

    async def update_package(self, source: str) -> dict[str, object]:
        current_session = self._require_current_session()
        update = getattr(current_session, "update_package", None)
        if not callable(update):
            raise RuntimeError("Package materializer is not available.")
        result = update(source)
        if inspect.isawaitable(result):
            return await result
        return result

    async def update_packages(self) -> list[dict[str, object]]:
        current_session = self._require_current_session()
        update = getattr(current_session, "update_packages", None)
        if not callable(update):
            raise RuntimeError("Package update is not available.")
        result = update()
        if inspect.isawaitable(result):
            return await result
        return result

    async def check_package_updates(self) -> list[dict[str, object]]:
        current_session = self._require_current_session()
        check = getattr(current_session, "check_package_updates", None)
        if not callable(check):
            raise RuntimeError("Package update check is not available.")
        result = check()
        if inspect.isawaitable(result):
            return await result
        return result

    async def remove_package(self, source: str) -> dict[str, object]:
        current_session = self._require_current_session()
        remove = getattr(current_session, "remove_package", None)
        if not callable(remove):
            raise RuntimeError("Package materializer is not available.")
        result = remove(source)
        if inspect.isawaitable(result):
            return await result
        return result

    async def uninstall_package(
        self, source: str, *, scope: str = "project"
    ) -> dict[str, object]:
        current_session = self._require_current_session()
        uninstall = getattr(current_session, "uninstall_package", None)
        if not callable(uninstall):
            raise RuntimeError("Package uninstallation is not available.")
        result = uninstall(source, scope=scope)
        if inspect.isawaitable(result):
            return await result
        return result

    async def dispose(self) -> None:
        await self.drain_session_index_flush()
        await self._lifecycle.dispose(
            reason="quit",
            metadata=self._lifecycle_metadata(operation="dispose"),
        )

    def _lifecycle_metadata(
        self,
        *,
        operation: str,
        options: dict[str, object] | None = None,
        **details: object,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {"operation": operation, **details}
        if options is not None:
            metadata["options"] = options
        return metadata

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
                target_session_file=_session_file_from_session(target_session),
            ),
        )

    async def _after_lifecycle_commit(
        self,
        result: _SessionOperationResult,
        transition: SessionLifecycleTransition,
    ) -> None:
        session = _require_operation_session(result)
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
                previous_session_file=_session_file_from_session(current),
            ),
        )

    async def _prepare_session_shutdown(
        self, session: AgentSession, event: SessionShutdownEvent
    ) -> None:
        try:
            await _emit_session_shutdown(session, event)
        except Exception as exc:
            self._record_session_shutdown_failure(session=session, event=event, exc=exc)
        finally:
            self._sync_session_extension_diagnostics(session)

    def _create_session(
        self, manager: SessionManager, start_event: SessionStartEvent
    ) -> AgentSession:
        if self._session_factory_accepts_start_event:
            return self.session_factory(manager, session_start_event=start_event)
        return self.session_factory(manager)

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
            current_session = self._current_session
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
            session_id=getattr(self._current_session, "session_id", None),
            details={
                "all_sessions": all_sessions,
                "session_dir": str(self.session_dir),
            },
        )

    def _record_session_operation_failure(
        self,
        *,
        code: str,
        exc: Exception,
        details: dict[str, object],
    ) -> None:
        diagnostics_service = self._diagnostics_service
        current_session = self._current_session
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
            session_id=_session_id_from_session(session),
            details={
                "reason": event.reason,
                "session_file": _session_file_from_session(session),
                "target_session_file": event.target_session_file,
            },
        )

    async def _run_replacement_callbacks(
        self,
        session: AgentSession,
        options: dict[str, object],
        *,
        include_setup: bool = False,
    ) -> None:
        with_session = options.get("withSession") or options.get("with_session")
        await run_replacement_callbacks(
            setup=options.get("setup") if include_setup else None,
            setup_argument=session.session_manager,
            after_setup=lambda: _sync_agent_messages_from_session_manager(session),
            with_session=with_session,
            session_argument=(
                _create_replaced_session_context(session)
                if callable(with_session)
                else None
            ),
            on_failure=lambda failure: self._record_replacement_callback_failure(
                session=session,
                callback_name=failure.name,
                exc=failure.error,
            ),
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
            session_id=_session_id_from_session(session),
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
                session_id=_session_id_from_session(session),
            )
            for diagnostic in diagnostics[recorded:]
        )
        try:
            setattr(session, recorded_attr, len(diagnostics))
        except Exception:
            return

    def _require_current_session(self) -> AgentSession:
        if self._current_session is None:
            raise RuntimeError("No active session")
        return self._current_session

    def _resolve_session_file(self, session_id: str | Path) -> Path:
        candidate = Path(session_id).expanduser()
        if candidate.exists():
            return candidate.resolve()

        session_name = candidate.name
        matches = sorted(self.session_dir.glob(f"*_{session_name}.jsonl"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous session reference: {session_name}")
        prefix_matches = [
            summary
            for summary in self.list_session_summaries()
            if summary.session_file is not None
            and summary.session_id.startswith(session_name)
        ]
        if len(prefix_matches) == 1 and prefix_matches[0].session_file is not None:
            return prefix_matches[0].session_file
        if len(prefix_matches) > 1:
            raise ValueError(f"Ambiguous session reference: {session_name}")
        raise FileNotFoundError(
            errno.ENOENT, "No such file or directory", str(candidate)
        )

    def _resolve_import_cwd(self, cwd: str | Path) -> str:
        candidate = Path(cwd).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(
                errno.ENOENT, "No such file or directory", str(candidate)
            )
        resolved = candidate.resolve()
        if not resolved.is_dir():
            raise NotADirectoryError(errno.ENOTDIR, "Not a directory", str(resolved))
        return str(resolved)

    def _get_extension_runner(self, session: AgentSession):
        return getattr(
            session, "extension_runner", getattr(session, "_extension_runner", None)
        )


def _accepts_session_start_event(factory: SessionFactory) -> bool:
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD or name == "session_start_event"
        for name, parameter in signature.parameters.items()
    )


def _require_operation_session(
    result: _SessionOperationResult,
) -> AgentSession:
    if result.current is None:
        raise RuntimeError("Session operation completed without an active session")
    return result.current


def _session_id_from_session(session: object) -> str | None:
    session_id = getattr(session, "session_id", None)
    if isinstance(session_id, str) and session_id:
        return session_id
    session_manager = getattr(session, "session_manager", None)
    get_header = getattr(session_manager, "get_header", None)
    if not callable(get_header):
        return None
    return getattr(get_header(), "conversation_id", None)


async def _emit_session_shutdown(
    session: AgentSession, event: SessionShutdownEvent
) -> None:
    runner = getattr(
        session, "extension_runner", getattr(session, "_extension_runner", None)
    )
    emitter = getattr(runner, "emit_session_shutdown", None)
    if callable(emitter):
        await emitter(event)


async def _dispose_session_only(session: AgentSession) -> None:
    dispose_after_shutdown = getattr(session, "_dispose_after_session_shutdown", None)
    if callable(dispose_after_shutdown):
        result = dispose_after_shutdown()
        if inspect.isawaitable(result):
            await result
        return

    invalidator = getattr(session, "_invalidate_extension_contexts", None)
    if callable(invalidator):
        invalidator("Extension context is stale after session replacement or shutdown.")
        unsubscribe = getattr(session, "_unsubscribe_agent", None)
        if callable(unsubscribe):
            unsubscribe()
        event_bus = getattr(session, "_runtime_event_bus", None)
        clear_event_bus = getattr(event_bus, "clear", None)
        if callable(clear_event_bus):
            clear_event_bus()
        clear_listeners = getattr(getattr(session, "_listeners", None), "clear", None)
        if callable(clear_listeners):
            clear_listeners()
        return

    dispose = session.dispose
    try:
        inspect.signature(dispose)
    except (TypeError, ValueError):
        await dispose()
        return
    await dispose()


def _diagnostics_query_for_session(
    query: DiagnosticsQuery | None, session_id: str
) -> DiagnosticsQuery:
    if query is None:
        return DiagnosticsQuery(session_id=session_id)
    return replace(query, session_id=session_id)


def _create_replaced_session_context(session: AgentSession) -> object:
    create_context = getattr(session, "create_replaced_session_context", None)
    if callable(create_context):
        return create_context()
    session_manager = getattr(session, "session_manager", None)
    cwd = session_manager.get_cwd() if session_manager is not None else None
    return SimpleNamespace(cwd=cwd, session_manager=session_manager)


def _replacement_callback_options(
    *,
    setup: object | None = None,
    with_session: object | None = None,
) -> dict[str, object]:
    options: dict[str, object] = {}
    if setup is not None:
        options["setup"] = setup
    if with_session is not None:
        options["with_session"] = with_session
    return options


def _sync_agent_messages_from_session_manager(session: AgentSession) -> None:
    agent = getattr(session, "agent", None)
    state = getattr(agent, "state", None)
    set_messages = getattr(state, "set_messages", None)
    if callable(set_messages):
        set_messages(session.session_manager.build_session_context().messages)


def _resolve_fork_target(
    manager: SessionManager, entry_id: str, *, position: str
) -> tuple[str | None, str | None]:
    if position == "at":
        return entry_id, None
    if position != "before":
        raise ValueError(f"Unsupported fork position: {position}")
    entry = manager.get_entry(entry_id)
    if (
        entry is None
        or entry.kind != AGENT_MESSAGE_KIND
        or not isinstance(entry.payload, UserMessage)
    ):
        raise ValueError("Fork position 'before' requires a user message entry.")
    return entry.parent_id, _user_message_text(entry.payload)


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


def _user_message_text(message: UserMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.text for part in content if isinstance(part, TextPart))
    return ""


def _session_file_from_session(session: AgentSession | None) -> str | None:
    if session is None:
        return None
    session_manager = getattr(session, "session_manager", None)
    if session_manager is None:
        return None
    return _session_file_from_manager(session_manager)


def _session_file_from_manager(manager: SessionManager) -> str | None:
    session_file = getattr(manager, "session_file", None)
    return str(session_file) if session_file is not None else None
