"""Product-neutral lifecycle operations for transcript-backed sessions.

The adapter is deliberately a mixin: a Product still supplies transcript
creation, session construction, lifecycle hooks, and error presentation while
Harness owns the public operation grammar and callback plumbing.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Generic, TypeVar

from loushang.harness.runtime import (
    SessionOperationResult,
    run_replacement_callbacks,
)
from loushang.harness.session.lifecycle import (
    MissingSessionCwdError,
    PreparedSessionLifecycleOperation,
)
from loushang.harness.session.transcript_lifecycle import (
    require_session_operation_session,
)

SessionT = TypeVar("SessionT")
PayloadT = TypeVar("PayloadT")


class SessionLifecycleOperationAdapter(Generic[SessionT, PayloadT]):
    """Shared public lifecycle surface for a Product session runtime.

    The concrete runtime must also inherit a transcript lifecycle runtime and
    provide ``_resolve_import_cwd`` plus the Product-specific hook methods used
    by replacement and diagnostics callbacks.
    """

    async def new_session(
        self,
        *,
        cwd: str | Path | None = None,
        parent_session: str | None = None,
    ) -> SessionT:
        result = await self.new_session_operation(
            cwd=cwd,
            parent_session=parent_session,
        )
        return require_session_operation_session(result)

    async def new_session_operation(
        self,
        *,
        cwd: str | Path | None = None,
        parent_session: str | None = None,
        setup: object | None = None,
        with_session: object | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT]:
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
    ) -> SessionOperationResult[SessionT, PayloadT]:
        return await super().new_session_operation(
            cwd=self._resolve_import_cwd(cwd) if cwd is not None else None,
            parent_session_ref=parent_session,
            metadata=self._lifecycle_metadata(
                operation="new_session",
                options=options,
                include_setup=True,
            ),
        )

    async def restore_session(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: str = "error",
    ) -> SessionT:
        result = await self.restore_session_operation(
            session_id,
            fallback_cwd=fallback_cwd,
            missing_cwd=missing_cwd,
        )
        return require_session_operation_session(result)

    async def switch_session(self, session_id: str | Path) -> SessionT:
        return await self.restore_session(session_id)

    async def restore_session_operation(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: str = "error",
        with_session: object | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT]:
        options = _replacement_callback_options(with_session=with_session)
        return await self._run_restore_session_operation(
            session_id,
            fallback_cwd=fallback_cwd,
            missing_cwd=missing_cwd,
            options=options or None,
        )

    async def prepare_restore_session_operation(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: str = "error",
    ) -> PreparedSessionLifecycleOperation[SessionT, PayloadT]:
        session_file = self.resolve_session_file(session_id)
        try:
            return await super().prepare_restore_session_operation(
                session_file,
                fallback_cwd=(str(fallback_cwd) if fallback_cwd is not None else None),
                missing_cwd=missing_cwd,
                metadata=self._lifecycle_metadata(
                    operation="restore_session",
                    session_ref=str(session_id),
                    target_session_file=str(session_file),
                    fallback_cwd=(
                        str(fallback_cwd) if fallback_cwd is not None else None
                    ),
                    missing_cwd=missing_cwd,
                ),
            )
        except MissingSessionCwdError as exc:
            raise self._translate_missing_cwd_error(exc) from exc

    async def _run_restore_session_operation(
        self,
        session_id: str | Path,
        *,
        fallback_cwd: str | Path | None = None,
        missing_cwd: str = "error",
        options: dict[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT]:
        session_file = self.resolve_session_file(session_id)
        try:
            return await super().restore_session_operation(
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
        except MissingSessionCwdError as exc:
            raise self._translate_missing_cwd_error(exc) from exc

    async def fork_session(
        self,
        entry_id: str,
        *,
        position: str = "at",
    ) -> SessionT:
        result = await self.fork_session_operation(entry_id, position=position)
        return require_session_operation_session(result)

    async def fork_session_operation(
        self,
        entry_id: str | None,
        *,
        position: str = "at",
        with_session: object | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT]:
        options = _replacement_callback_options(with_session=with_session)
        return await self._run_fork_session_operation(
            entry_id,
            position=position,
            options=options or None,
        )

    async def _run_fork_session_operation(
        self,
        entry_id: str | None,
        *,
        position: str = "at",
        options: dict[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT]:
        return await super().fork_session_operation(
            entry_id,
            position=position,
            metadata=self._lifecycle_metadata(
                operation="fork_session",
                options=options,
            ),
        )

    async def clone_session(self) -> SessionT:
        result = await self.clone_session_operation()
        return require_session_operation_session(result)

    async def clone_session_operation(
        self,
    ) -> SessionOperationResult[SessionT, PayloadT]:
        return await self._run_fork_session_operation(None)

    async def import_from_jsonl(
        self,
        input_path: str | Path,
        cwd_override: str | Path | None = None,
    ) -> dict[str, bool]:
        result = await self.import_session_operation(
            input_path,
            cwd_override=cwd_override,
        )
        return {"cancelled": result.cancelled}

    async def import_session_operation(
        self,
        input_path: str | Path,
        *,
        cwd_override: str | Path | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT]:
        source = Path(input_path).expanduser().resolve()
        try:
            return await super().import_session_operation(
                source,
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
        except MissingSessionCwdError as exc:
            raise self._translate_missing_cwd_error(exc) from exc

    async def replace_current_session(self, session: SessionT) -> None:
        await super().replace_current_session(
            session,
            metadata=self._lifecycle_metadata(
                operation="replace_current_session",
                activate_extensions=False,
                emit_before_transition=False,
                schedule_index=False,
            ),
        )

    def get_packages(
        self, *, catalog_path: str | None = None
    ) -> list[dict[str, object]]:
        current_session = self.session
        getter = getattr(current_session, "get_packages", None)
        if not callable(getter):
            return []
        return getter(catalog_path=catalog_path)

    async def materialize_package(self, source: str) -> dict[str, object]:
        return await _call_session_operation(
            self.session,
            "materialize_package",
            source,
            unavailable="Package materializer is not available.",
        )

    async def install_package(
        self,
        source: str,
        *,
        scope: str = "project",
    ) -> dict[str, object]:
        return await _call_session_operation(
            self.session,
            "install_package",
            source,
            scope=scope,
            unavailable="Package installation is not available.",
        )

    async def update_package(self, source: str) -> dict[str, object]:
        return await _call_session_operation(
            self.session,
            "update_package",
            source,
            unavailable="Package materializer is not available.",
        )

    async def update_packages(self) -> list[dict[str, object]]:
        return await _call_session_operation(
            self.session,
            "update_packages",
            unavailable="Package update is not available.",
        )

    async def check_package_updates(self) -> list[dict[str, object]]:
        return await _call_session_operation(
            self.session,
            "check_package_updates",
            unavailable="Package update check is not available.",
        )

    async def remove_package(self, source: str) -> dict[str, object]:
        return await _call_session_operation(
            self.session,
            "remove_package",
            source,
            unavailable="Package materializer is not available.",
        )

    async def uninstall_package(
        self,
        source: str,
        *,
        scope: str = "project",
    ) -> dict[str, object]:
        return await _call_session_operation(
            self.session,
            "uninstall_package",
            source,
            scope=scope,
            unavailable="Package uninstallation is not available.",
        )

    async def dispose(self) -> None:
        await self.dispose_session_runtime(
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

    def _translate_missing_cwd_error(self, error: MissingSessionCwdError) -> Exception:
        """Allow a Product to preserve its public error type when required."""

        return error

    async def _run_replacement_callbacks(
        self,
        session: SessionT,
        options: dict[str, object],
        *,
        include_setup: bool = False,
    ) -> None:
        with_session = options.get("withSession") or options.get("with_session")
        await run_replacement_callbacks(
            setup=options.get("setup") if include_setup else None,
            setup_argument=getattr(session, "session_manager", None),
            after_setup=lambda: _sync_agent_messages_from_session(session),
            with_session=with_session,
            session_argument=_replacement_context(session)
            if callable(with_session)
            else None,
            on_failure=lambda failure: self._record_replacement_callback_failure(
                session=session,
                callback_name=failure.name,
                exc=failure.error,
            ),
        )

    async def _run_replacement_callbacks_for_result(
        self,
        result: SessionOperationResult[SessionT, PayloadT],
        transition: object,
    ) -> None:
        del transition
        options = getattr(result, "options", None)
        if isinstance(options, dict):
            await self._run_replacement_callbacks(result.current, options)


async def _call_session_operation(
    session: object,
    name: str,
    *args: object,
    unavailable: str,
    **kwargs: object,
) -> object:
    operation = getattr(session, name, None)
    if not callable(operation):
        raise RuntimeError(unavailable)
    result = operation(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


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


def _sync_agent_messages_from_session(session: object) -> None:
    agent = getattr(session, "agent", None)
    state = getattr(agent, "state", None)
    set_messages = getattr(state, "set_messages", None)
    manager = getattr(session, "session_manager", None)
    build_context = getattr(manager, "build_session_context", None)
    if callable(set_messages) and callable(build_context):
        set_messages(build_context().messages)


def _replacement_context(session: object) -> object:
    create_context = getattr(session, "create_replaced_session_context", None)
    if callable(create_context):
        return create_context()
    manager = getattr(session, "session_manager", None)
    get_cwd = getattr(manager, "get_cwd", None)
    return SimpleNamespace(
        cwd=get_cwd() if callable(get_cwd) else None,
        session_manager=manager,
    )


__all__ = ["SessionLifecycleOperationAdapter"]
