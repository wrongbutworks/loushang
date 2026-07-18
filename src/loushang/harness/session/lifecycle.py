from __future__ import annotations

import errno
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Literal, Protocol, TypeVar

from loushang.harness.runtime import (
    CancelledSessionOperation,
    SessionOperationCandidate,
    SessionOperationCoordinator,
    SessionOperationFailure,
    SessionOperationPhase,
    SessionOperationResult,
    SessionTransitionHost,
    copy_file_exclusive,
    stage_file_import,
)

SessionT = TypeVar("SessionT")
PayloadT = TypeVar("PayloadT")
SessionLifecycleReason = str
MissingCwdPolicy = Literal["error", "fallback"]

SessionCallback = Callable[[SessionT], Awaitable[None] | None]
TransitionCandidateCallback = Callable[
    [SessionT, SessionT | None, "SessionLifecycleTransition"],
    Awaitable[None] | None,
]
TransitionReleaseCallback = Callable[
    [SessionT, SessionT | None, "SessionLifecycleTransition"],
    Awaitable[None] | None,
]
LifecycleCallback = Callable[[], Awaitable[None] | None]
FileCopy = Callable[[Path, Path], None]


@dataclass(frozen=True)
class SessionLifecycleTransition:
    """A product-neutral active-session transition request."""

    reason: SessionLifecycleReason
    cwd: str | None = None
    target_session_ref: str | None = None
    parent_session_ref: str | None = None
    fork_entry_id: str | None = None
    fork_position: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionLifecycleDecision:
    """A hook result that can cancel a pending lifecycle transition."""

    cancelled: bool = False


@dataclass(frozen=True)
class SessionCwdIssue:
    session_cwd: str
    session_ref: str | None = None
    fallback_cwd: str | None = None


class MissingSessionCwdError(RuntimeError):
    def __init__(self, issue: SessionCwdIssue) -> None:
        message = f"Session cwd is not available: {issue.session_cwd}"
        if issue.session_ref is not None:
            message = f"{message} ({issue.session_ref})"
        if issue.fallback_cwd is not None:
            message = f"{message}. Fallback cwd: {issue.fallback_cwd}"
        super().__init__(message)
        self.issue = issue


@dataclass(frozen=True)
class ForkProfile:
    """Product-configurable fork-position contract.

    Harness provides a conservative default that forks *at* the selected entry.
    Products can opt into additional positions, such as Coding's ``before``
    behavior, by adding the position and injecting a matching target resolver.
    """

    default_position: str = "at"
    supported_positions: frozenset[str] = frozenset({"at"})

    def __post_init__(self) -> None:
        if not self.default_position:
            raise ValueError("Fork profile default_position must not be blank")
        if not self.supported_positions:
            raise ValueError("Fork profile must support at least one position")
        if self.default_position not in self.supported_positions:
            raise ValueError(
                "Fork profile default_position must be one of supported_positions"
            )

    def resolve_position(self, position: str | None) -> str:
        resolved = self.default_position if position is None else position
        if resolved not in self.supported_positions:
            supported = ", ".join(sorted(self.supported_positions))
            raise ValueError(
                f"Unsupported fork position: {resolved}. Supported positions: {supported}"
            )
        return resolved


DEFAULT_FORK_PROFILE = ForkProfile()


@dataclass(frozen=True)
class ForkSelection(Generic[PayloadT]):
    """Resolved fork target plus optional product presentation payload."""

    target_entry_id: str | None
    payload: PayloadT | None = None


class SessionLifecycleStore(Protocol[SessionT]):
    """Product storage/session port used by the lifecycle runtime.

    ``restore`` may raise :class:`MissingSessionCwdError` before constructing a
    Product session. This lets a store validate restored metadata without
    starting Product resources that would immediately be discarded.
    """

    async def create(
        self,
        current_session: SessionT | None,
        transition: SessionLifecycleTransition,
        *,
        cwd: str,
        parent_session_ref: str | None,
    ) -> SessionT: ...

    async def restore(
        self,
        current_session: SessionT | None,
        transition: SessionLifecycleTransition,
        session_ref: str | Path,
        *,
        cwd_override: str | None = None,
    ) -> SessionT: ...

    async def fork(
        self,
        session: SessionT,
        transition: SessionLifecycleTransition,
        target_entry_id: str | None,
    ) -> SessionT: ...

    def get_cwd(self, session: SessionT) -> str: ...

    def get_session_ref(self, session: SessionT) -> str | None: ...

    def get_leaf_entry_id(self, session: SessionT) -> str | None: ...


ForkTargetResolver = Callable[[SessionT, str, str], ForkSelection[PayloadT]]
BeforeTransitionHook = Callable[
    [SessionT | None, SessionLifecycleTransition],
    Awaitable[SessionLifecycleDecision | None] | SessionLifecycleDecision | None,
]
FailureHook = Callable[
    [SessionOperationFailure[SessionT], SessionLifecycleTransition],
    Awaitable[None] | None,
]


@dataclass(frozen=True)
class SessionLifecycleHooks(Generic[SessionT, PayloadT]):
    """Product lifecycle effects around common transition transactions."""

    before_transition: BeforeTransitionHook[SessionT] | None = None
    prepare_session: TransitionCandidateCallback[SessionT] | None = None
    activate_session: TransitionCandidateCallback[SessionT] | None = None
    before_release: TransitionReleaseCallback[SessionT] | None = None
    dispose_session: SessionCallback[SessionT] | None = None
    after_commit: (
        Callable[
            [
                SessionOperationResult[SessionT, PayloadT | None],
                SessionLifecycleTransition,
            ],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    on_failure: FailureHook[SessionT] | None = None


class SessionLifecycleRuntime(Generic[SessionT, PayloadT]):
    """Reusable active-session lifecycle coordinator.

    It coordinates storage operations and active-session replacement without
    knowing transcript formats, product hooks, extension event classes, UI, or
    fork-content semantics. Products implement those details through ports.
    """

    def __init__(
        self,
        *,
        store: SessionLifecycleStore[SessionT],
        hooks: SessionLifecycleHooks[SessionT, PayloadT],
        current_session: SessionT | None = None,
        fork_profile: ForkProfile = DEFAULT_FORK_PROFILE,
        fork_target_resolver: ForkTargetResolver[SessionT, PayloadT] | None = None,
        copy_file: FileCopy = copy_file_exclusive,
    ) -> None:
        if hooks.dispose_session is None:
            raise ValueError("Session lifecycle hooks require dispose_session.")
        self.store = store
        self.hooks = hooks
        self._dispose_session = hooks.dispose_session
        self.fork_profile = fork_profile
        self._fork_target_resolver = fork_target_resolver or _default_fork_target
        self._copy_file = copy_file
        self._host = SessionTransitionHost(
            current_session,
            dispose=self._dispose_session,
        )
        self._operations = SessionOperationCoordinator(self._host)

    @property
    def current_session(self) -> SessionT | None:
        return self._host.current

    @property
    def transition_host(self) -> SessionTransitionHost[SessionT]:
        """Expose the shared host for product-only serialized operations."""

        return self._host

    @property
    def session(self) -> SessionT:
        current = self.current_session
        if current is None:
            raise RuntimeError("No active session")
        return current

    def set_rebind_session(self, callback: SessionCallback[SessionT] | None) -> None:
        self._host.set_rebind(callback)

    def set_before_session_invalidate(self, callback: LifecycleCallback | None) -> None:
        self._host.set_before_invalidate(callback)

    def subscribe_before_session_invalidate(
        self, callback: LifecycleCallback
    ) -> Callable[[], None]:
        return self._host.subscribe_before_invalidate(callback)

    def subscribe_after_session_invalidate(
        self, callback: LifecycleCallback
    ) -> Callable[[], None]:
        return self._host.subscribe_after_invalidate(callback)

    async def new(
        self,
        *,
        cwd: str | None = None,
        parent_session_ref: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        async with self._host.transition():
            resolved_cwd = cwd
            if resolved_cwd is None:
                current = self.session
                resolved_cwd = self.store.get_cwd(current)
            transition = SessionLifecycleTransition(
                reason="new",
                cwd=resolved_cwd,
                parent_session_ref=parent_session_ref,
                metadata=metadata or {},
            )
            return await self._run(
                transition,
                lambda current: self.store.create(
                    current,
                    transition,
                    cwd=resolved_cwd,
                    parent_session_ref=parent_session_ref,
                ),
            )

    async def restore(
        self,
        session_ref: str | Path,
        *,
        fallback_cwd: str | None = None,
        missing_cwd: MissingCwdPolicy = "error",
        metadata: Mapping[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        transition = SessionLifecycleTransition(
            reason="resume",
            target_session_ref=str(session_ref),
            metadata=metadata or {},
        )

        async def _restore(current: SessionT | None) -> SessionT:
            try:
                session = await self.store.restore(current, transition, session_ref)
            except MissingSessionCwdError as exc:
                if missing_cwd != "fallback" or fallback_cwd is None:
                    raise _with_fallback_cwd(exc, fallback_cwd) from exc
                return await self.store.restore(
                    current,
                    transition,
                    session_ref,
                    cwd_override=fallback_cwd,
                )
            issue = self._missing_cwd_issue(session, fallback_cwd=fallback_cwd)
            if issue is None:
                return session
            if missing_cwd != "fallback" or fallback_cwd is None:
                raise MissingSessionCwdError(issue)
            return await self.store.restore(
                current,
                transition,
                session_ref,
                cwd_override=fallback_cwd,
            )

        return await self._run(transition, _restore)

    async def fork(
        self,
        entry_id: str | None = None,
        *,
        position: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        async with self._host.transition():
            current = self.session
            resolved_entry_id = entry_id or self.store.get_leaf_entry_id(current)
            if not isinstance(resolved_entry_id, str) or not resolved_entry_id:
                raise ValueError("Cannot fork session: no current entry selected")
            resolved_position = self.fork_profile.resolve_position(position)
            selection = self._fork_target_resolver(
                current, resolved_entry_id, resolved_position
            )
            transition = SessionLifecycleTransition(
                reason="fork",
                cwd=self.store.get_cwd(current),
                parent_session_ref=self.store.get_session_ref(current),
                fork_entry_id=resolved_entry_id,
                fork_position=resolved_position,
                metadata=metadata or {},
            )
            return await self._run(
                transition,
                lambda _current: self.store.fork(
                    current, transition, selection.target_entry_id
                ),
                payload=selection.payload,
            )

    async def import_file(
        self,
        input_path: str | Path,
        *,
        destination_dir: Path,
        cwd_override: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        source = Path(input_path).expanduser().resolve()
        preflight = SessionLifecycleTransition(
            reason="resume",
            target_session_ref=str(source),
            metadata=metadata or {},
        )
        try:
            if not source.exists():
                raise FileNotFoundError(
                    errno.ENOENT, "No such file or directory", str(source)
                )
            staged = stage_file_import(
                source,
                destination_dir,
                copy_file=self._copy_file,
            )
        except Exception as exc:
            await self._notify_preflight_failure(preflight, exc)
            raise
        transition = SessionLifecycleTransition(
            reason="resume",
            target_session_ref=str(staged.destination),
            metadata=metadata or {},
        )

        async def _restore(current: SessionT | None) -> SessionT:
            session = await self.store.restore(
                current,
                transition,
                staged.destination,
                cwd_override=cwd_override,
            )
            issue = self._missing_cwd_issue(session, fallback_cwd=cwd_override)
            if issue is not None:
                raise MissingSessionCwdError(issue)
            return session

        try:
            return await self._run(
                transition,
                _restore,
                rollback=staged.cleanup,
            )
        except BaseException:
            staged.cleanup()
            raise

    async def replace(
        self,
        session: SessionT,
        *,
        reason: SessionLifecycleReason = "resume",
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        transition = SessionLifecycleTransition(
            reason=reason,
            target_session_ref=self.store.get_session_ref(session),
            metadata=metadata or {},
        )
        await self._run(transition, lambda _current: _completed(session))

    async def dispose(
        self,
        *,
        reason: SessionLifecycleReason = "quit",
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        current = self.current_session
        if current is None:
            return
        transition = SessionLifecycleTransition(
            reason=reason,
            target_session_ref=self.store.get_session_ref(current),
            metadata=metadata or {},
        )
        await self._host.dispose_current(
            before_release=lambda session: self._before_release(
                session,
                target_session=None,
                transition=transition,
            )
        )

    async def _run(
        self,
        transition: SessionLifecycleTransition,
        create_session: Callable[[SessionT | None], Awaitable[SessionT] | SessionT],
        *,
        payload: PayloadT | None = None,
        rollback: LifecycleCallback | None = None,
    ) -> SessionOperationResult[SessionT, PayloadT | None]:
        async def _prepare(
            current: SessionT | None,
        ) -> (
            SessionOperationCandidate[SessionT, PayloadT | None]
            | CancelledSessionOperation[PayloadT | None]
        ):
            decision = await _maybe_await(
                self.hooks.before_transition(current, transition)
                if self.hooks.before_transition is not None
                else None
            )
            if decision is not None and decision.cancelled:
                return CancelledSessionOperation(payload, cleanup=rollback)
            session = await _maybe_await(create_session(current))

            async def _rollback() -> None:
                try:
                    await _maybe_await(self._dispose_session(session))
                finally:
                    if rollback is not None:
                        await _maybe_await(rollback())

            return SessionOperationCandidate(
                session=session,
                payload=payload,
                rollback=_rollback,
            )

        async def _after_commit(
            result: SessionOperationResult[SessionT, PayloadT | None],
        ) -> None:
            if self.hooks.after_commit is not None:
                await _maybe_await(self.hooks.after_commit(result, transition))

        async def _on_failure(failure: SessionOperationFailure[SessionT]) -> None:
            if self.hooks.on_failure is not None:
                await _maybe_await(self.hooks.on_failure(failure, transition))

        prepare_session = self.hooks.prepare_session
        activate_session = self.hooks.activate_session
        return await self._operations.run(
            _prepare,
            prepare_session=(
                None
                if prepare_session is None
                else lambda candidate, previous: prepare_session(
                    candidate.session, previous, transition
                )
            ),
            before_release=lambda previous, candidate: self._before_release(
                previous,
                target_session=candidate.session,
                transition=transition,
            ),
            activate=(
                None
                if activate_session is None
                else lambda candidate, previous: activate_session(
                    candidate.session, previous, transition
                )
            ),
            after_commit=_after_commit,
            on_failure=_on_failure,
        )

    async def _before_release(
        self,
        session: SessionT,
        *,
        target_session: SessionT | None,
        transition: SessionLifecycleTransition,
    ) -> None:
        if self.hooks.before_release is not None:
            await _maybe_await(
                self.hooks.before_release(session, target_session, transition)
            )

    def _missing_cwd_issue(
        self, session: SessionT, *, fallback_cwd: str | None
    ) -> SessionCwdIssue | None:
        cwd = self.store.get_cwd(session)
        candidate = Path(cwd).expanduser()
        if candidate.exists() and candidate.is_dir():
            return None
        return SessionCwdIssue(
            session_cwd=cwd,
            session_ref=self.store.get_session_ref(session),
            fallback_cwd=fallback_cwd,
        )

    async def _notify_preflight_failure(
        self,
        transition: SessionLifecycleTransition,
        error: Exception,
    ) -> None:
        if self.hooks.on_failure is None:
            return
        current = self.current_session
        await _maybe_await(
            self.hooks.on_failure(
                SessionOperationFailure(
                    phase=SessionOperationPhase.PREPARE,
                    error=error,
                    previous=current,
                    current=current,
                ),
                transition,
            )
        )


def _default_fork_target(
    _session: SessionT, entry_id: str, position: str
) -> ForkSelection[PayloadT]:
    if position != "at":
        raise ValueError(
            "The default Harness fork profile supports only the 'at' position."
        )
    return ForkSelection(target_entry_id=entry_id)


def _with_fallback_cwd(
    error: MissingSessionCwdError,
    fallback_cwd: str | None,
) -> MissingSessionCwdError:
    if error.issue.fallback_cwd == fallback_cwd:
        return error
    return MissingSessionCwdError(
        SessionCwdIssue(
            session_cwd=error.issue.session_cwd,
            session_ref=error.issue.session_ref,
            fallback_cwd=fallback_cwd,
        )
    )


async def _completed(value: SessionT) -> SessionT:
    return value


async def _maybe_await(value: Awaitable[PayloadT] | PayloadT) -> PayloadT:
    return await value if inspect.isawaitable(value) else value


__all__ = [
    "DEFAULT_FORK_PROFILE",
    "FileCopy",
    "ForkProfile",
    "ForkSelection",
    "ForkTargetResolver",
    "MissingCwdPolicy",
    "MissingSessionCwdError",
    "SessionCwdIssue",
    "SessionLifecycleDecision",
    "SessionLifecycleHooks",
    "SessionLifecycleReason",
    "SessionLifecycleRuntime",
    "SessionLifecycleStore",
    "SessionLifecycleTransition",
    "TransitionCandidateCallback",
    "TransitionReleaseCallback",
]
