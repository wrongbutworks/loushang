"""Generic product session runtime composition.

This module owns the adapter that joins the existing transcript directory,
lifecycle transaction, and operation runtimes.  It does not implement another
session engine: products provide transcript/session ports and lifecycle hooks,
while the inherited Harness runtimes continue to own the algorithms.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from loushang.harness.agent_transcript import SessionSummary
from loushang.harness.runtime import copy_file_exclusive
from loushang.harness.session.diagnostics import SessionDiagnosticsRuntime
from loushang.harness.session.lifecycle import (
    ForkProfile,
    ForkTargetResolver,
    MissingSessionCwdError,
    SessionLifecycleHooks,
    SessionLifecycleRuntime,
    SessionLifecycleStore,
    SessionLifecycleTransition,
)
from loushang.harness.session.lifecycle_adapter import (
    SessionLifecycleOperationAdapter,
)
from loushang.harness.session.transcript_lifecycle import (
    AgentTranscriptSessionRuntime,
    ProductTranscriptSessionLifecyclePorts,
    ProductTranscriptSessionLifecycleStore,
)

SessionT = TypeVar("SessionT")
TranscriptT = TypeVar("TranscriptT")
PayloadT = TypeVar("PayloadT")

SessionBuilder = Callable[
    [TranscriptT, SessionT | None, SessionLifecycleTransition],
    SessionT | Awaitable[SessionT],
]
TranscriptValidator = Callable[[TranscriptT], None | Awaitable[None]]
RenameTranscript = Callable[
    [Path, str | None], SessionSummary | Awaitable[SessionSummary]
]
DeleteTranscript = Callable[[Path, str | None], bool | Awaitable[bool]]
OperationFailureRecorder = Callable[
    [str, Exception, dict[str, object]], None
]
ReplacementFailureRecorder = Callable[..., None]


@dataclass(frozen=True)
class ProductSessionRuntimePorts(Generic[SessionT, TranscriptT, PayloadT]):
    """Product bindings required by :class:`ProductSessionRuntime`.

    The ports intentionally contain no Coding, UI, provider, or wire-schema
    types.  Fork semantics, diagnostics, extension lifecycle, and transcript
    storage remain Product decisions; this object only gives the shared
    runtime a stable composition boundary.
    """

    session_factory: Callable[..., SessionT]
    persist: bool
    create_transcript: Callable[
        [str, str | None], TranscriptT | Awaitable[TranscriptT]
    ]
    restore_transcript: Callable[
        [str | Path, str | None], TranscriptT | Awaitable[TranscriptT]
    ]
    fork_transcript: Callable[
        [TranscriptT, str | None], TranscriptT | Awaitable[TranscriptT]
    ]
    dispose_transcript: Callable[[TranscriptT], None | Awaitable[None]]
    transcript_for_session: Callable[[SessionT], TranscriptT]
    transcript_cwd: Callable[[TranscriptT], str]
    transcript_session_ref: Callable[[TranscriptT], str | None]
    transcript_leaf_entry_id: Callable[[TranscriptT], str | None]
    build_session: SessionBuilder[SessionT, TranscriptT]
    validate_restored_transcript: TranscriptValidator[TranscriptT] | None
    fork_profile: ForkProfile
    fork_target_resolver: ForkTargetResolver[SessionT, PayloadT]
    copy_file: Callable[[Path, Path], None] = copy_file_exclusive
    hooks: SessionLifecycleHooks[SessionT, PayloadT] = SessionLifecycleHooks()
    diagnostics_runtime: SessionDiagnosticsRuntime | Callable[
        [SessionT | None], SessionDiagnosticsRuntime
    ] | None = None
    record_index_refresh_failure: Callable[[Exception, bool], None] | None = None
    rename_transcript: RenameTranscript | None = None
    delete_transcript: DeleteTranscript | None = None
    current_session_file: Callable[[SessionT | None], str | None] | None = None
    record_operation_failure: OperationFailureRecorder | None = None
    record_replacement_callback_failure: ReplacementFailureRecorder | None = None
    resolve_import_cwd: Callable[[str | Path], str] | None = None
    translate_missing_cwd_error: Callable[[MissingSessionCwdError], Exception] | None = None


class ProductSessionRuntime(
    SessionLifecycleOperationAdapter[SessionT, PayloadT],
    AgentTranscriptSessionRuntime[SessionT, PayloadT],
    Generic[SessionT, TranscriptT, PayloadT],
):
    """Compose standard session runtimes for any Agent product.

    ``SessionLifecycleRuntime`` remains the transaction owner and
    ``AgentTranscriptSessionRuntime`` remains the directory/index owner.  This
    class only wires their existing ports and supplies common rename/delete
    operations.  Product-specific hooks are passed through unchanged.
    """

    def __init__(
        self,
        *,
        session_dir: str | Path,
        ports: ProductSessionRuntimePorts[SessionT, TranscriptT, PayloadT],
        current_session: SessionT | None = None,
        auto_refresh_session_index: bool = False,
        session_index_refresh_interval: float = 0.5,
        session_index_flush_delay: float = 0.25,
    ) -> None:
        self._product_runtime_ports = ports
        self.session_factory = ports.session_factory
        self.persist = ports.persist
        lifecycle_store: SessionLifecycleStore[SessionT] = (
            ProductTranscriptSessionLifecycleStore(
                ports=ProductTranscriptSessionLifecyclePorts(
                    create_transcript=ports.create_transcript,
                    restore_transcript=ports.restore_transcript,
                    fork_transcript=ports.fork_transcript,
                    dispose_transcript=ports.dispose_transcript,
                    transcript_for_session=ports.transcript_for_session,
                    transcript_cwd=ports.transcript_cwd,
                    transcript_session_ref=ports.transcript_session_ref,
                    transcript_leaf_entry_id=ports.transcript_leaf_entry_id,
                ),
                build_session=ports.build_session,
                validate_restored_transcript=ports.validate_restored_transcript,
            )
        )
        lifecycle = SessionLifecycleRuntime(
            store=lifecycle_store,
            current_session=current_session,
            fork_profile=ports.fork_profile,
            fork_target_resolver=ports.fork_target_resolver,
            copy_file=ports.copy_file,
            hooks=ports.hooks,
        )
        diagnostics_runtime = ports.diagnostics_runtime
        if diagnostics_runtime is not None and not callable(diagnostics_runtime):
            fixed_diagnostics_runtime = diagnostics_runtime

            def fixed_runtime(_session: SessionT | None) -> SessionDiagnosticsRuntime:
                return fixed_diagnostics_runtime

            diagnostics_runtime = fixed_runtime
        super().__init__(
            session_dir=session_dir,
            lifecycle=lifecycle,
            auto_refresh_session_index=auto_refresh_session_index,
            session_index_refresh_interval=session_index_refresh_interval,
            session_index_flush_delay=session_index_flush_delay,
            diagnostics_runtime=diagnostics_runtime,
            record_index_refresh_failure=ports.record_index_refresh_failure,
        )

    async def create_session(
        self,
        *,
        cwd: str,
        parent_session: str | None = None,
    ) -> SessionT:
        return await self.new_session(cwd=cwd, parent_session=parent_session)

    async def rename_session(
        self,
        session_id: str | Path,
        name: str | None,
    ) -> SessionSummary:
        if self._product_runtime_ports.rename_transcript is None:
            raise RuntimeError("Session rename is not available.")
        session_file: Path | None = None
        try:
            session_file = self.resolve_session_file(session_id)
            summary = self._product_runtime_ports.rename_transcript(session_file, name)
            if inspect.isawaitable(summary):
                summary = await summary
            if self.auto_refresh_session_index:
                self.request_session_index_refresh()
            return summary
        except Exception as exc:
            self._record_operation_failure(
                "session_rename_failed",
                exc,
                {
                    "operation": "rename_session",
                    "session_ref": str(session_id),
                    "target_session_file": (
                        str(session_file) if session_file is not None else None
                    ),
                    "name": name,
                },
            )
            raise

    async def delete_session(self, session_id: str | Path) -> bool:
        if self._product_runtime_ports.delete_transcript is None:
            raise RuntimeError("Session deletion is not available.")
        session_file: Path | None = None
        try:
            session_file = self.resolve_session_file(session_id)
            current_file = (
                self._product_runtime_ports.current_session_file(self.current_session)
                if self._product_runtime_ports.current_session_file is not None
                else None
            )
            deleted = self._product_runtime_ports.delete_transcript(
                session_file,
                current_file,
            )
            if inspect.isawaitable(deleted):
                deleted = await deleted
            if deleted and self.auto_refresh_session_index:
                self.request_session_index_refresh()
            return deleted
        except Exception as exc:
            self._record_operation_failure(
                "session_delete_failed",
                exc,
                {
                    "operation": "delete_session",
                    "session_ref": str(session_id),
                    "target_session_file": (
                        str(session_file) if session_file is not None else None
                    ),
                },
            )
            raise

    def _record_operation_failure(
        self,
        code: str,
        exc: Exception,
        details: dict[str, object],
    ) -> None:
        recorder = self._product_runtime_ports.record_operation_failure
        if recorder is not None:
            recorder(code, exc, details)

    def _record_replacement_callback_failure(
        self,
        *,
        session: SessionT,
        callback_name: str,
        exc: Exception,
    ) -> None:
        recorder = self._product_runtime_ports.record_replacement_callback_failure
        if recorder is not None:
            recorder(session=session, callback_name=callback_name, exc=exc)

    def _resolve_import_cwd(self, cwd: str | Path) -> str:
        resolver = self._product_runtime_ports.resolve_import_cwd
        if resolver is None:
            return str(Path(cwd).expanduser().resolve())
        return resolver(cwd)

    def _translate_missing_cwd_error(
        self,
        error: MissingSessionCwdError,
    ) -> Exception:
        translator = self._product_runtime_ports.translate_missing_cwd_error
        return translator(error) if translator is not None else error


def invoke_session_factory(
    factory: Callable[..., SessionT],
    transcript: TranscriptT,
    *,
    session_start_event: object,
) -> SessionT:
    """Invoke a Product factory with the optional lifecycle event contract."""

    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        signature = None
    accepts_event = signature is not None and any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        or name == "session_start_event"
        for name, parameter in signature.parameters.items()
    )
    if accepts_event:
        return factory(transcript, session_start_event=session_start_event)
    return factory(transcript)


def session_id_from_session(session: object | None) -> str | None:
    if session is None:
        return None
    session_id = getattr(session, "session_id", None)
    if isinstance(session_id, str) and session_id:
        return session_id
    manager = getattr(session, "session_manager", None)
    get_header = getattr(manager, "get_header", None)
    if not callable(get_header):
        return None
    value = getattr(get_header(), "conversation_id", None)
    return value if isinstance(value, str) else None


def session_file_from_manager(manager: object | None) -> str | None:
    if manager is None:
        return None
    value = getattr(manager, "session_file", None)
    return str(value) if value is not None else None


def session_file_from_session(session: object | None) -> str | None:
    return session_file_from_manager(getattr(session, "session_manager", None))


def session_manager_ref(manager: object) -> str | None:
    getter = getattr(manager, "get_session_file", None)
    if not callable(getter):
        return session_file_from_manager(manager)
    value = getter()
    return str(value) if value is not None else None


async def emit_session_shutdown(session: object, event: object) -> None:
    runner = getattr(
        session,
        "extension_runner",
        getattr(session, "_extension_runner", None),
    )
    emitter = getattr(runner, "emit_session_shutdown", None)
    if callable(emitter):
        result = emitter(event)
        if inspect.isawaitable(result):
            await result


async def dispose_session_only(session: object) -> None:
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
    dispose = getattr(session, "dispose", None)
    if not callable(dispose):
        return
    result = dispose()
    if inspect.isawaitable(result):
        await result


def resolve_existing_cwd(cwd: str | Path) -> str:
    """Resolve an import cwd while preserving filesystem error types."""

    candidate = Path(cwd).expanduser()
    if not candidate.exists():
        raise FileNotFoundError(2, "No such file or directory", str(candidate))
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise NotADirectoryError(20, "Not a directory", str(resolved))
    return str(resolved)


__all__ = [
    "ProductSessionRuntime",
    "ProductSessionRuntimePorts",
    "dispose_session_only",
    "emit_session_shutdown",
    "invoke_session_factory",
    "resolve_existing_cwd",
    "session_file_from_manager",
    "session_file_from_session",
    "session_id_from_session",
    "session_manager_ref",
]
