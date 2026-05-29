from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
import errno
import inspect
from pathlib import Path
from shutil import copyfileobj
from time import monotonic
from types import SimpleNamespace
from typing import Literal

from loushang.ai.types import TextPart, UserMessage
from loushang.coding.diagnostics import DiagnosticRecord, DiagnosticSummary, DiagnosticsQuery, DiagnosticsService, ErrorReport
from loushang.coding.extensions import SessionBeforeForkEvent, SessionBeforeSwitchEvent, SessionShutdownEvent, SessionStartEvent
from loushang.coding.message import SessionMessageEntry
from loushang.coding.session import AgentSession
from loushang.coding.store import SessionManager, SessionQuery, SessionRecord, SessionSummary


SessionFactory = Callable[..., AgentSession]
SessionRebindCallback = Callable[[AgentSession], Awaitable[None]]
BeforeSessionInvalidateCallback = Callable[[], None]


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


class AgentSessionRuntime:
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
        self.session_dir = Path(session_dir)
        self.session_factory = session_factory
        self._session_factory_accepts_start_event = _accepts_session_start_event(session_factory)
        self.persist = persist
        self._current_session = current_session
        self._diagnostics_service = diagnostics_service
        self.auto_refresh_session_index = auto_refresh_session_index
        self.session_index_refresh_interval = session_index_refresh_interval
        self.session_index_flush_delay = session_index_flush_delay
        self._last_session_index_refresh = 0.0
        self._session_index_flush_task: asyncio.Task[None] | None = None
        self._session_index_flush_all_sessions = False
        self._replacement_lock = asyncio.Lock()
        self._replacement_lock_owner: asyncio.Task[object] | None = None
        self._replacement_lock_depth = 0
        self._rebind_session: SessionRebindCallback | None = None
        self._before_session_invalidate: BeforeSessionInvalidateCallback | None = None
        if current_session is not None:
            self._bind_runtime_host(current_session)

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
        self._rebind_session = callback

    def set_before_session_invalidate(self, callback: BeforeSessionInvalidateCallback | None) -> None:
        self._before_session_invalidate = callback

    async def create_session(self, *, cwd: str, parent_session: str | None = None) -> AgentSession:
        return await self.new_session(cwd=cwd, parent_session=parent_session)

    async def new_session(self, *, cwd: str | Path | None = None, parent_session: str | None = None) -> AgentSession:
        async with self._replacement_guard():
            return await self._new_session_unlocked(cwd=cwd, parent_session=parent_session)

    async def _new_session_unlocked(
        self,
        *,
        cwd: str | Path | None = None,
        parent_session: str | None = None,
    ) -> AgentSession:
        current_session = self._current_session
        resolved_cwd = self._resolve_cwd(cwd)
        if current_session is not None:
            runner = self._get_extension_runner(current_session)
            if runner is not None:
                decision = await runner.before_session_switch(SessionBeforeSwitchEvent(reason="new", cwd=resolved_cwd))
                self._sync_session_extension_diagnostics(current_session)
                if decision is not None and decision.cancel:
                    return current_session
        manager = SessionManager.new(
            session_dir=self.session_dir,
            cwd=resolved_cwd,
            persist=self.persist,
            parent_session=parent_session,
        )
        return await self._replace_with_manager(
            manager,
            start_event=SessionStartEvent(
                reason="new" if current_session is not None else "startup",
                previous_session_file=_session_file_from_session(current_session),
            ),
            shutdown_event=SessionShutdownEvent(reason="new", target_session_file=_session_file_from_manager(manager)),
        )

    async def newSession(self, options: object | None = None) -> dict[str, bool]:
        opts = options if isinstance(options, dict) else {}
        async with self._replacement_guard():
            previous = self._current_session
            parent_candidate = opts.get("parentSession", opts.get("parent_session"))
            parent_session = parent_candidate if isinstance(parent_candidate, str) else None
            cwd = opts.get("cwd")
            session = await self._new_session_unlocked(
                cwd=cwd if isinstance(cwd, str | Path) else None,
                parent_session=parent_session,
            )
            if session is not previous:
                await self._run_replacement_callbacks(session, opts, include_setup=True)
            return {"cancelled": session is previous}

    async def switch_session(self, session_id: str | Path) -> AgentSession:
        return await self.restore_session(session_id)

    async def switchSession(self, session_path: str | Path, options: object | None = None) -> dict[str, bool]:
        opts = options if isinstance(options, dict) else {}
        async with self._replacement_guard():
            previous = self._current_session
            session = await self._restore_session_unlocked(session_path)
            if session is not previous:
                await self._run_replacement_callbacks(session, opts)
            return {"cancelled": session is previous}

    async def restore_session(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: Literal["error", "fallback"] = "error",
    ) -> AgentSession:
        async with self._replacement_guard():
            return await self._restore_session_unlocked(
                session_id,
                fallback_cwd=fallback_cwd,
                missing_cwd=missing_cwd,
            )

    async def _restore_session_unlocked(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: Literal["error", "fallback"] = "error",
    ) -> AgentSession:
        current_session = self._current_session
        session_file: Path | None = None
        try:
            session_file = self._resolve_session_file(session_id)
            if current_session is not None:
                runner = self._get_extension_runner(current_session)
                if runner is not None:
                    decision = await runner.before_session_switch(
                        SessionBeforeSwitchEvent(
                            reason="resume",
                            cwd=current_session.session_manager.get_cwd(),
                            target_session_file=str(session_file),
                        )
                    )
                    self._sync_session_extension_diagnostics(current_session)
                    if decision is not None and decision.cancel:
                        return current_session
            manager = SessionManager.open(session_file, session_dir=self.session_dir, persist=self.persist)
            missing_issue = get_missing_session_cwd_issue(manager, fallback_cwd=fallback_cwd)
            if missing_issue is not None:
                if missing_cwd != "fallback" or fallback_cwd is None:
                    raise MissingSessionCwdError(missing_issue)
                resolved_fallback_cwd = self._resolve_import_cwd(fallback_cwd)
                manager = SessionManager.open(
                    session_file,
                    session_dir=self.session_dir,
                    cwd_override=resolved_fallback_cwd,
                    persist=self.persist,
                )
            return await self._replace_with_manager(
                manager,
                start_event=SessionStartEvent(
                    reason="resume",
                    previous_session_file=_session_file_from_session(current_session),
                ),
                shutdown_event=SessionShutdownEvent(reason="resume", target_session_file=_session_file_from_manager(manager)),
            )
        except Exception as exc:
            self._record_session_operation_failure(
                code="session_restore_failed",
                exc=exc,
                details={
                    "operation": "restore_session",
                    "session_ref": str(session_id),
                    "target_session_file": str(session_file) if session_file is not None else None,
                    "fallback_cwd": str(fallback_cwd) if fallback_cwd is not None else None,
                    "missing_cwd": missing_cwd,
                },
            )
            raise

    async def fork_session(self, entry_id: str, *, position: str = "at") -> AgentSession:
        async with self._replacement_guard():
            session, _selected_text = await self._fork_session_with_result_unlocked(entry_id, position=position)
            return session

    async def fork_session_with_result(self, entry_id: str, *, position: str = "at") -> tuple[AgentSession, str | None]:
        async with self._replacement_guard():
            return await self._fork_session_with_result_unlocked(entry_id, position=position)

    async def _fork_session_with_result_unlocked(
        self,
        entry_id: str,
        *,
        position: str = "at",
    ) -> tuple[AgentSession, str | None]:
        current = self._require_current_session()
        fork_target_id, selected_text = _resolve_fork_target(current.session_manager, entry_id, position=position)
        runner = self._get_extension_runner(current)
        decision = await runner.before_session_fork(
            SessionBeforeForkEvent(
                entry_id=entry_id,
                cwd=current.session_manager.get_cwd(),
                position=position,
            )
        ) if runner is not None else None
        if runner is not None:
            self._sync_session_extension_diagnostics(current)
        if decision is not None and decision.cancel:
            return current, selected_text
        manager = (
            SessionManager.new(
                session_dir=self.session_dir,
                cwd=current.session_manager.get_cwd(),
                persist=self.persist,
                parent_session=_session_file_from_session(current),
            )
            if fork_target_id is None
            else current.session_manager.fork(fork_target_id)
        )
        next_session = await self._replace_with_manager(
            manager,
            start_event=SessionStartEvent(reason="fork", previous_session_file=_session_file_from_session(current)),
            shutdown_event=SessionShutdownEvent(reason="fork", target_session_file=_session_file_from_manager(manager)),
        )
        return next_session, selected_text

    async def fork(self, entry_id: str, options: object | None = None) -> dict[str, object]:
        opts = options if isinstance(options, dict) else {}
        position = opts.get("position", "before")
        if position not in {"before", "at"}:
            raise ValueError(f"Unsupported fork position: {position}")
        async with self._replacement_guard():
            previous = self._current_session
            session, selected_text = await self._fork_session_with_result_unlocked(entry_id, position=position)
            if session is not previous:
                await self._run_replacement_callbacks(session, opts)
            result: dict[str, object] = {"cancelled": session is previous}
            if selected_text is not None:
                result["selectedText"] = selected_text
                result["selected_text"] = selected_text
            return result

    async def clone_session(self) -> AgentSession:
        async with self._replacement_guard():
            current = self._require_current_session()
            leaf_id = current.session_manager.get_leaf_id()
            if not isinstance(leaf_id, str) or not leaf_id:
                raise ValueError("Cannot clone session: no current entry selected")
            return (await self._fork_session_with_result_unlocked(leaf_id))[0]

    async def clone(self) -> dict[str, bool]:
        async with self._replacement_guard():
            previous = self._current_session
            current = self._require_current_session()
            leaf_id = current.session_manager.get_leaf_id()
            if not isinstance(leaf_id, str) or not leaf_id:
                raise ValueError("Cannot clone session: no current entry selected")
            session, _selected_text = await self._fork_session_with_result_unlocked(leaf_id)
            return {"cancelled": session is previous}

    async def import_from_jsonl(
        self, input_path: str | Path, cwd_override: str | Path | None = None
    ) -> dict[str, bool]:
        async with self._replacement_guard():
            return await self._import_from_jsonl_unlocked(input_path, cwd_override)

    async def _import_from_jsonl_unlocked(
        self, input_path: str | Path, cwd_override: str | Path | None = None
    ) -> dict[str, bool]:
        current_session = self._current_session
        source: Path | None = None
        destination: Path | None = None
        try:
            source = Path(input_path).expanduser().resolve()
            if not source.exists():
                raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(source))

            skipped_destinations: set[Path] = set()
            while True:
                destination = _unique_import_destination(self.session_dir, source, skipped=skipped_destinations)
                self.session_dir.mkdir(parents=True, exist_ok=True)
                copied_destination = False
                try:
                    if destination != source:
                        _copy_import_file(source, destination)
                        copied_destination = True
                except FileExistsError:
                    skipped_destinations.add(destination)
                    continue

                try:
                    if current_session is not None:
                        runner = self._get_extension_runner(current_session)
                        if runner is not None:
                            decision = await runner.before_session_switch(
                                SessionBeforeSwitchEvent(
                                    reason="resume",
                                    cwd=current_session.session_manager.get_cwd(),
                                    target_session_file=str(destination),
                                )
                            )
                            self._sync_session_extension_diagnostics(current_session)
                            if decision is not None and decision.cancel:
                                if copied_destination:
                                    _unlink_path(destination)
                                return {"cancelled": True}

                    cwd = self._resolve_import_cwd(cwd_override) if cwd_override is not None else None
                    manager = SessionManager.open(
                        destination,
                        session_dir=self.session_dir,
                        cwd_override=cwd,
                        persist=self.persist,
                    )
                    self._raise_if_session_cwd_missing(manager, fallback_cwd=cwd)
                except Exception:
                    if copied_destination:
                        _unlink_path(destination)
                    raise
                break
            await self._replace_with_manager(
                manager,
                start_event=SessionStartEvent(
                    reason="resume",
                    previous_session_file=_session_file_from_session(current_session),
                ),
                shutdown_event=SessionShutdownEvent(reason="resume", target_session_file=_session_file_from_manager(manager)),
            )
            return {"cancelled": False}
        except Exception as exc:
            self._record_session_operation_failure(
                code="session_import_failed",
                exc=exc,
                details={
                    "operation": "import_from_jsonl",
                    "input_path": str(input_path),
                    "source_path": str(source) if source is not None else None,
                    "target_session_file": str(destination) if destination is not None else None,
                    "cwd_override": str(cwd_override) if cwd_override is not None else None,
                },
            )
            raise

    async def importFromJsonl(self, input_path: str | Path, cwd_override: str | Path | None = None) -> dict[str, bool]:
        return await self.import_from_jsonl(input_path, cwd_override)

    async def replace_current_session(self, session: AgentSession) -> None:
        async with self._replacement_guard():
            await self._replace_current_session_unlocked(session)

    async def _replace_current_session_unlocked(self, session: AgentSession) -> None:
        previous = self._current_session
        if previous is not None and previous is not session:
            await self._dispose_current_session(
                previous,
                SessionShutdownEvent(reason="resume", target_session_file=_session_file_from_session(session)),
            )
            self._current_session = None
        self._bind_runtime_host(session)
        self._current_session = session
        await self._run_rebind_session(session)

    def get_current_session(self) -> AgentSession | None:
        return self._current_session

    def list_sessions(self) -> list[SessionRecord]:
        return SessionManager.list(self.session_dir)

    def list_session_summaries(self) -> list[SessionSummary]:
        return SessionManager.list_summaries(self.session_dir)

    def find_session_summaries(self, query: SessionQuery | None = None) -> list[SessionSummary]:
        return SessionManager.find_sessions(self.session_dir, query)

    def rename_session(self, session_id: str | Path, name: str | None) -> SessionSummary:
        session_file: Path | None = None
        try:
            session_file = self._resolve_session_file(session_id)
            summary = SessionManager.rename_session(session_file, name)
            if self.auto_refresh_session_index:
                self._schedule_session_index_flush()
            return summary
        except Exception as exc:
            self._record_session_operation_failure(
                code="session_rename_failed",
                exc=exc,
                details={
                    "operation": "rename_session",
                    "session_ref": str(session_id),
                    "target_session_file": str(session_file) if session_file is not None else None,
                    "name": name,
                },
            )
            raise

    def delete_session(self, session_id: str | Path) -> bool:
        session_file: Path | None = None
        try:
            session_file = self._resolve_session_file(session_id)
            deleted = SessionManager.delete_session(
                session_file,
                current_session_file=_session_file_from_session(self._current_session),
            )
            if deleted and self.auto_refresh_session_index:
                self._schedule_session_index_flush()
            return deleted
        except Exception as exc:
            self._record_session_operation_failure(
                code="session_delete_failed",
                exc=exc,
                details={
                    "operation": "delete_session",
                    "session_ref": str(session_id),
                    "target_session_file": str(session_file) if session_file is not None else None,
                },
            )
            raise

    def list_all_session_summaries(self) -> list[SessionSummary]:
        return SessionManager.list_all_summaries(self.session_dir.parent)

    def find_all_session_summaries(self, query: SessionQuery | None = None) -> list[SessionSummary]:
        return SessionManager.find_all_sessions(self.session_dir.parent, query)

    def refresh_session_index(self) -> list[SessionSummary]:
        return SessionManager.refresh_index(self.session_dir)

    def refresh_all_session_indexes(self) -> list[SessionSummary]:
        return SessionManager.refresh_all_indexes(self.session_dir.parent)

    def list_indexed_session_summaries(self, *, refresh: bool = False) -> list[SessionSummary]:
        if self.auto_refresh_session_index and not refresh:
            self._schedule_session_index_flush_if_due()
        return SessionManager.list_indexed_summaries(self.session_dir, refresh=refresh)

    def find_indexed_session_summaries(self, query: SessionQuery | None = None) -> list[SessionSummary]:
        return SessionManager.find_indexed_sessions(self.session_dir, query)

    def list_all_indexed_session_summaries(self, *, refresh: bool = False) -> list[SessionSummary]:
        if self.auto_refresh_session_index and not refresh:
            self._schedule_session_index_flush_if_due(all_sessions=True)
        return SessionManager.list_all_indexed_summaries(self.session_dir.parent, refresh=refresh)

    def find_all_indexed_session_summaries(self, query: SessionQuery | None = None) -> list[SessionSummary]:
        return SessionManager.find_all_indexed_sessions(self.session_dir.parent, query)

    def get_last_diagnostics(self, limit: int = 50) -> list[DiagnosticRecord]:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = current_session.diagnostics_service if current_session is not None else None
        if diagnostics_service is None:
            return []
        return diagnostics_service.get_last_diagnostics(limit=limit)

    def get_diagnostics(self, query: DiagnosticsQuery | None = None) -> list[DiagnosticRecord]:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = current_session.diagnostics_service if current_session is not None else None
        if diagnostics_service is None:
            return []
        return diagnostics_service.get_diagnostics(query=query)

    def get_session_diagnostics(self, query: DiagnosticsQuery | None = None) -> list[DiagnosticRecord]:
        current_session = self._require_current_session()
        getter = getattr(current_session, "get_session_diagnostics", None)
        if callable(getter):
            return getter(query)
        diagnostics_service = self._diagnostics_service or current_session.diagnostics_service
        if diagnostics_service is None:
            return []
        return diagnostics_service.get_diagnostics(query=_diagnostics_query_for_session(query, current_session.session_id))

    def get_diagnostics_summary(self, query: DiagnosticsQuery | None = None) -> DiagnosticSummary:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = current_session.diagnostics_service if current_session is not None else None
        if diagnostics_service is None:
            return DiagnosticsService().get_diagnostics_summary(query=query)
        return diagnostics_service.get_diagnostics_summary(query=query)

    def get_session_diagnostics_summary(self, query: DiagnosticsQuery | None = None) -> DiagnosticSummary:
        current_session = self._require_current_session()
        diagnostics_service = self._diagnostics_service or current_session.diagnostics_service
        if diagnostics_service is None:
            return DiagnosticsService().get_diagnostics_summary(query=query)
        return diagnostics_service.get_diagnostics_summary(query=_diagnostics_query_for_session(query, current_session.session_id))

    def get_last_error_report(self) -> ErrorReport | None:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = current_session.diagnostics_service if current_session is not None else None
        if diagnostics_service is None:
            return None
        return diagnostics_service.get_last_error_report()

    def get_packages(self, *, catalog_path: str | None = None) -> list[dict[str, object]]:
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

    async def install_package(self, source: str, *, scope: str = "project") -> dict[str, object]:
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

    async def uninstall_package(self, source: str, *, scope: str = "project") -> dict[str, object]:
        current_session = self._require_current_session()
        uninstall = getattr(current_session, "uninstall_package", None)
        if not callable(uninstall):
            raise RuntimeError("Package uninstallation is not available.")
        result = uninstall(source, scope=scope)
        if inspect.isawaitable(result):
            return await result
        return result

    async def dispose(self) -> None:
        async with self._replacement_guard():
            await self.drain_session_index_flush()
            if self._current_session is not None:
                await self._dispose_current_session(self._current_session, SessionShutdownEvent(reason="quit"))
                self._current_session = None

    async def drain_session_index_flush(self) -> None:
        task = self._session_index_flush_task
        if task is None:
            return
        all_sessions = self._session_index_flush_all_sessions
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        try:
            self._flush_session_index_now(all_sessions=all_sessions, raise_on_error=False)
        finally:
            self._session_index_flush_task = None
            self._session_index_flush_all_sessions = False

    async def _replace_with_manager(
        self,
        manager: SessionManager,
        *,
        start_event: SessionStartEvent,
        shutdown_event: SessionShutdownEvent,
    ) -> AgentSession:
        previous = self._current_session
        next_session = self._create_session(manager, start_event)
        self._bind_runtime_host(next_session)
        if previous is not None:
            await self._dispose_current_session(previous, shutdown_event)
            self._current_session = None
        self._current_session = next_session
        starter = getattr(next_session, "start_extension_runtime", None)
        if callable(starter):
            await starter(reason=start_event.reason)
        await self._run_rebind_session(next_session)
        if self.auto_refresh_session_index:
            self._schedule_session_index_flush()
        return next_session

    async def _dispose_current_session(self, session: AgentSession, event: SessionShutdownEvent) -> None:
        try:
            await _emit_session_shutdown(session, event)
        except Exception as exc:
            self._record_session_shutdown_failure(session=session, event=event, exc=exc)
        finally:
            self._sync_session_extension_diagnostics(session)
        if self._before_session_invalidate is not None:
            self._before_session_invalidate()
        await _dispose_session_only(session)

    async def _run_rebind_session(self, session: AgentSession) -> None:
        if self._rebind_session is not None:
            await self._rebind_session(session)

    def _refresh_session_index_now(self) -> list[SessionSummary]:
        summaries = SessionManager.refresh_index(self.session_dir)
        self._last_session_index_refresh = monotonic()
        return summaries

    def _refresh_all_session_indexes_now(self) -> list[SessionSummary]:
        summaries = SessionManager.refresh_all_indexes(self.session_dir.parent)
        self._last_session_index_refresh = monotonic()
        return summaries

    def _flush_session_index_now(self, *, all_sessions: bool, raise_on_error: bool = True) -> list[SessionSummary]:
        try:
            if all_sessions:
                return self._refresh_all_session_indexes_now()
            return self._refresh_session_index_now()
        except Exception as exc:
            self._record_session_index_flush_failure(exc, all_sessions=all_sessions)
            if raise_on_error:
                raise
            return []

    def _schedule_session_index_flush_if_due(self, *, all_sessions: bool = False) -> None:
        if self._session_index_refresh_due():
            self._schedule_session_index_flush(all_sessions=all_sessions)

    def _schedule_session_index_flush(self, *, all_sessions: bool = False) -> None:
        self._session_index_flush_all_sessions = self._session_index_flush_all_sessions or all_sessions
        task = self._session_index_flush_task
        if task is not None and not task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._flush_session_index_now(
                all_sessions=self._session_index_flush_all_sessions,
                raise_on_error=False,
            )
            self._session_index_flush_all_sessions = False
            return
        self._session_index_flush_task = loop.create_task(self._delayed_session_index_flush())

    async def _delayed_session_index_flush(self) -> None:
        try:
            await asyncio.sleep(max(0.0, self.session_index_flush_delay))
            self._flush_session_index_now(
                all_sessions=self._session_index_flush_all_sessions,
                raise_on_error=False,
            )
        finally:
            self._session_index_flush_task = None
            self._session_index_flush_all_sessions = False

    def _session_index_refresh_due(self) -> bool:
        return monotonic() - self._last_session_index_refresh >= self.session_index_refresh_interval

    def _create_session(self, manager: SessionManager, start_event: SessionStartEvent) -> AgentSession:
        if self._session_factory_accepts_start_event:
            return self.session_factory(manager, session_start_event=start_event)
        return self.session_factory(manager)

    def _bind_runtime_host(self, session: AgentSession) -> None:
        setter = getattr(session, "set_extension_runtime_host", None)
        if callable(setter):
            setter(self)

    @asynccontextmanager
    async def _replacement_guard(self) -> AsyncIterator[None]:
        task = asyncio.current_task()
        if task is not None and self._replacement_lock_owner is task:
            self._replacement_lock_depth += 1
            try:
                yield
            finally:
                self._replacement_lock_depth -= 1
            return

        await self._replacement_lock.acquire()
        self._replacement_lock_owner = task
        self._replacement_lock_depth = 1
        try:
            yield
        finally:
            self._replacement_lock_depth -= 1
            if self._replacement_lock_depth == 0:
                self._replacement_lock_owner = None
                self._replacement_lock.release()

    def _record_session_index_flush_failure(self, exc: Exception, *, all_sessions: bool) -> None:
        diagnostics_service = self._diagnostics_service
        if diagnostics_service is None:
            current_session = self._current_session
            diagnostics_service = current_session.diagnostics_service if current_session is not None else None
        if diagnostics_service is None:
            return
        diagnostics_service.capture_failure(
            code="session_index_refresh_failed",
            error=exc,
            phase="runtime",
            source="session",
            session_id=getattr(self._current_session, "session_id", None),
            details={"all_sessions": all_sessions, "session_dir": str(self.session_dir)},
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
        diagnostics_service = self._diagnostics_service or getattr(session, "diagnostics_service", None)
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
        if include_setup:
            setup = options.get("setup")
            if callable(setup):
                try:
                    await _await_replacement_callback(setup, session.session_manager, name="setup")
                except Exception as exc:
                    self._record_replacement_callback_failure(
                        session=session,
                        callback_name="setup",
                        exc=exc,
                    )
                    raise
                _sync_agent_messages_from_session_manager(session)
        with_session = options.get("withSession") or options.get("with_session")
        if callable(with_session):
            try:
                await _await_replacement_callback(
                    with_session,
                    _create_replaced_session_context(session),
                    name="withSession",
                )
            except Exception as exc:
                self._record_replacement_callback_failure(
                    session=session,
                    callback_name="withSession",
                    exc=exc,
                )
                raise

    def _record_replacement_callback_failure(
        self,
        *,
        session: AgentSession,
        callback_name: str,
        exc: Exception,
    ) -> None:
        diagnostics_service = self._diagnostics_service or getattr(session, "diagnostics_service", None)
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

    def _sync_session_extension_diagnostics(self, session: AgentSession, *, phase: str = "runtime") -> None:
        sync = getattr(session, "_sync_extension_diagnostics", None)
        if callable(sync):
            sync(phase=phase)
            return

        diagnostics_service = self._diagnostics_service or getattr(session, "diagnostics_service", None)
        if diagnostics_service is None:
            return
        runner = self._get_extension_runner(session)
        get_diagnostics = getattr(runner, "get_diagnostics", None) if runner is not None else None
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

    def _resolve_cwd(self, cwd: str | Path | None) -> str:
        if cwd is None:
            return self._require_current_session().session_manager.get_cwd()

        candidate = Path(cwd).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(candidate))
        resolved = candidate.resolve()
        if not resolved.is_dir():
            raise NotADirectoryError(errno.ENOTDIR, "Not a directory", str(resolved))
        return str(resolved)

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
            if summary.session_file is not None and summary.session_id.startswith(session_name)
        ]
        if len(prefix_matches) == 1 and prefix_matches[0].session_file is not None:
            return prefix_matches[0].session_file
        if len(prefix_matches) > 1:
            raise ValueError(f"Ambiguous session reference: {session_name}")
        raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(candidate))

    def _resolve_import_cwd(self, cwd: str | Path) -> str:
        candidate = Path(cwd).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(candidate))
        resolved = candidate.resolve()
        if not resolved.is_dir():
            raise NotADirectoryError(errno.ENOTDIR, "Not a directory", str(resolved))
        return str(resolved)

    def _get_extension_runner(self, session: AgentSession):
        return getattr(session, "extension_runner", getattr(session, "_extension_runner", None))

    def _raise_if_session_cwd_missing(
        self,
        manager: SessionManager,
        *,
        fallback_cwd: str | Path | None = None,
    ) -> None:
        issue = get_missing_session_cwd_issue(manager, fallback_cwd=fallback_cwd)
        if issue is not None:
            raise MissingSessionCwdError(issue)


def _accepts_session_start_event(factory: SessionFactory) -> bool:
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD or name == "session_start_event"
        for name, parameter in signature.parameters.items()
    )


def _unique_import_destination(session_dir: Path, source: Path, *, skipped: set[Path] | None = None) -> Path:
    skipped = skipped or set()
    destination = (session_dir / source.name).resolve()
    if destination == source or (destination not in skipped and not destination.exists()):
        return destination

    stem = destination.stem
    suffix = destination.suffix
    for index in range(1, 10_000):
        candidate = destination.with_name(f"{stem}-import-{index}{suffix}").resolve()
        if candidate not in skipped and not candidate.exists():
            return candidate
    raise FileExistsError(errno.EEXIST, "No available import destination", str(destination))


def _copy_import_file(source: Path, destination: Path) -> None:
    created = False
    try:
        with source.open("rb") as input_handle:
            with destination.open("xb") as output_handle:
                created = True
                copyfileobj(input_handle, output_handle)
    except Exception:
        if created:
            _unlink_path(destination)
        raise


def _unlink_path(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _session_id_from_session(session: object) -> str | None:
    session_id = getattr(session, "session_id", None)
    if isinstance(session_id, str) and session_id:
        return session_id
    session_manager = getattr(session, "session_manager", None)
    get_header = getattr(session_manager, "get_header", None)
    if not callable(get_header):
        return None
    return getattr(get_header(), "id", None)


async def _emit_session_shutdown(session: AgentSession, event: SessionShutdownEvent) -> None:
    runner = getattr(session, "extension_runner", getattr(session, "_extension_runner", None))
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
        event_bus = getattr(session, "_event_bus", None)
        clear_event_bus = getattr(event_bus, "clear", None)
        if callable(clear_event_bus):
            clear_event_bus()
        listeners = getattr(session, "_listeners", None)
        if hasattr(listeners, "clear"):
            listeners.clear()
        return

    dispose = session.dispose
    try:
        inspect.signature(dispose)
    except (TypeError, ValueError):
        await dispose()
        return
    await dispose()


def _diagnostics_query_for_session(query: DiagnosticsQuery | None, session_id: str) -> DiagnosticsQuery:
    if query is None:
        return DiagnosticsQuery(session_id=session_id)
    return replace(query, session_id=session_id)


def _create_replaced_session_context(session: AgentSession) -> object:
    create_context = getattr(session, "create_replaced_session_context", None)
    if callable(create_context):
        return create_context()
    create_context = getattr(session, "createReplacedSessionContext", None)
    if callable(create_context):
        return create_context()
    session_manager = getattr(session, "session_manager", None)
    cwd = session_manager.get_cwd() if session_manager is not None else None
    return SimpleNamespace(cwd=cwd, sessionManager=session_manager, session_manager=session_manager)


def _sync_agent_messages_from_session_manager(session: AgentSession) -> None:
    agent = getattr(session, "agent", None)
    state = getattr(agent, "state", None)
    set_messages = getattr(state, "set_messages", None)
    if callable(set_messages):
        set_messages(session.session_manager.build_session_context().messages)


async def _await_replacement_callback(callback: object, *args: object, name: str) -> None:
    if not _is_async_callable(callback):
        raise TypeError(f"{name} callback must be an async callable.")
    await callback(*args)


def _is_async_callable(value: object) -> bool:
    if inspect.iscoroutinefunction(value):
        return True
    call = getattr(value, "__call__", None)
    return inspect.iscoroutinefunction(call)


def _resolve_fork_target(manager: SessionManager, entry_id: str, *, position: str) -> tuple[str | None, str | None]:
    if position == "at":
        return entry_id, None
    if position != "before":
        raise ValueError(f"Unsupported fork position: {position}")
    entry = manager.get_entry(entry_id)
    if not isinstance(entry, SessionMessageEntry) or not isinstance(entry.message, UserMessage):
        raise ValueError("Fork position 'before' requires a user message entry.")
    return entry.parent_id, _user_message_text(entry.message)


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
