"""Active-session facade for Products using the Agent transcript profile.

The transcript directory runtime owns discovery and index scheduling, while
``SessionLifecycleRuntime`` owns replacement transactions. This facade joins
those existing mechanisms into the standard Product-facing lifecycle surface
without selecting a store, transcript binding, Product hooks, or presentation.
"""

from __future__ import annotations

import errno
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Generic, TypeVar

from loushang.harness.agent_transcript.directory import (
    AgentTranscriptDirectoryRuntime,
)
from loushang.harness.runtime import SessionOperationResult
from loushang.harness.session.lifecycle import MissingCwdPolicy, SessionLifecycleRuntime

SessionT = TypeVar("SessionT")
PayloadT = TypeVar("PayloadT")

SessionCallback = Callable[[SessionT], Awaitable[None] | None]
LifecycleCallback = Callable[[], Awaitable[None] | None]


class AgentTranscriptSessionRuntime(
    AgentTranscriptDirectoryRuntime,
    Generic[SessionT, PayloadT],
):
    """Expose common active-session operations over one Agent transcript root.

    Products configure the lifecycle store, fork profile, lifecycle hooks, and
    metadata on the supplied ``SessionLifecycleRuntime``. This facade only
    delegates standard new, restore, fork, import, replacement, and disposal
    operations, together with current Native session-reference resolution.
    """

    def __init__(
        self,
        *,
        session_dir: str | Path,
        lifecycle: SessionLifecycleRuntime[SessionT, PayloadT],
        auto_refresh_session_index: bool = False,
        session_index_refresh_interval: float = 0.5,
        session_index_flush_delay: float = 0.25,
        record_index_refresh_failure: Callable[[Exception, bool], None] | None = None,
    ) -> None:
        super().__init__(
            session_dir=session_dir,
            auto_refresh_session_index=auto_refresh_session_index,
            session_index_refresh_interval=session_index_refresh_interval,
            session_index_flush_delay=session_index_flush_delay,
            record_index_refresh_failure=record_index_refresh_failure,
        )
        self._lifecycle = lifecycle

    @property
    def lifecycle(self) -> SessionLifecycleRuntime[SessionT, PayloadT]:
        """Return the Product-configured transaction runtime."""

        return self._lifecycle

    @property
    def current_session(self) -> SessionT | None:
        return self._lifecycle.current_session

    @property
    def session(self) -> SessionT:
        return self._lifecycle.session

    @property
    def cwd(self) -> str:
        return self._lifecycle.store.get_cwd(self.session)

    def set_rebind_session(self, callback: SessionCallback[SessionT] | None) -> None:
        self._lifecycle.set_rebind_session(callback)

    def set_before_session_invalidate(
        self,
        callback: LifecycleCallback | None,
    ) -> None:
        self._lifecycle.set_before_session_invalidate(callback)

    def subscribe_before_session_invalidate(
        self,
        callback: LifecycleCallback,
    ) -> Callable[[], None]:
        return self._lifecycle.subscribe_before_session_invalidate(callback)

    def subscribe_after_session_invalidate(
        self,
        callback: LifecycleCallback,
    ) -> Callable[[], None]:
        return self._lifecycle.subscribe_after_session_invalidate(callback)

    async def new_session_operation(
        self,
        *,
        cwd: str | None = None,
        parent_session_ref: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        return await self._lifecycle.new(
            cwd=cwd,
            parent_session_ref=parent_session_ref,
            metadata=metadata,
        )

    async def restore_session_operation(
        self,
        session_ref: str | Path,
        *,
        fallback_cwd: str | None = None,
        missing_cwd: MissingCwdPolicy = "error",
        metadata: dict[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        return await self._lifecycle.restore(
            session_ref,
            fallback_cwd=fallback_cwd,
            missing_cwd=missing_cwd,
            metadata=metadata,
        )

    async def fork_session_operation(
        self,
        entry_id: str | None,
        *,
        position: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        return await self._lifecycle.fork(
            entry_id,
            position=position,
            metadata=metadata,
        )

    async def import_session_operation(
        self,
        input_path: str | Path,
        *,
        cwd_override: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        return await self._lifecycle.import_file(
            input_path,
            destination_dir=self.session_dir,
            cwd_override=cwd_override,
            metadata=metadata,
        )

    async def replace_current_session(
        self,
        session: SessionT,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self._lifecycle.replace(session, metadata=metadata)

    async def dispose_session_runtime(
        self,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self.drain_session_index_flush()
        await self._lifecycle.dispose(reason="quit", metadata=metadata)

    def get_current_session(self) -> SessionT | None:
        return self.current_session

    def resolve_session_file(self, session_ref: str | Path) -> Path:
        """Resolve an exact path, filename, or unambiguous current-session id."""

        candidate = Path(session_ref).expanduser()
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
            errno.ENOENT,
            "No such file or directory",
            str(candidate),
        )


def require_session_operation_session(
    result: SessionOperationResult[SessionT, PayloadT | None],
) -> SessionT:
    """Return a completed operation's active session with a stable error."""

    if result.current is None:
        raise RuntimeError("Session operation completed without an active session")
    return result.current


__all__ = [
    "AgentTranscriptSessionRuntime",
    "require_session_operation_session",
]
