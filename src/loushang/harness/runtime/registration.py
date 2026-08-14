"""Owner-scoped lifecycle primitives for exact live registrations."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, TypeVar
from uuid import uuid4

RegistrationOwnerKind = Literal[
    "product",
    "oem",
    "extension",
    "capability",
    "session",
    "runtime",
]
RegistrationDisposalState = Literal[
    "removed",
    "already_removed",
    "failed_retryable",
    "failed_terminal",
]
RegistrationLeaseState = Literal[
    "active",
    "disposing",
    "disposed",
    "failed_retryable",
    "failed_terminal",
]
RegistrationScopeState = Literal[
    "open",
    "committed",
    "disposing",
    "disposed",
    "failed_retryable",
    "failed_terminal",
]

_OWNER_KINDS = frozenset(
    {"product", "oem", "extension", "capability", "session", "runtime"}
)
_DISPOSAL_STATES = frozenset(
    {"removed", "already_removed", "failed_retryable", "failed_terminal"}
)


@dataclass(frozen=True)
class RegistrationOwner:
    """Stable owner identity for one runtime generation."""

    owner_kind: RegistrationOwnerKind
    owner_id: str
    runtime_id: str
    generation: int

    def __post_init__(self) -> None:
        if self.owner_kind not in _OWNER_KINDS:
            raise ValueError(f"unsupported registration owner kind: {self.owner_kind}")
        _require_nonempty(self.owner_id, name="registration owner id")
        _require_nonempty(self.runtime_id, name="registration runtime id")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int):
            raise TypeError("registration owner generation must be an integer")
        if self.generation < 0:
            raise ValueError("registration owner generation must not be negative")


@dataclass(frozen=True)
class RegistrationIdentity:
    """Opaque exact identity, distinct from a registry's public lookup key."""

    surface: str
    registration_id: str
    public_key: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.surface, name="registration surface")
        _require_nonempty(self.registration_id, name="registration id")
        if self.public_key is not None:
            _require_nonempty(self.public_key, name="registration public key")

    @classmethod
    def create(
        cls,
        *,
        surface: str,
        public_key: str | None = None,
    ) -> RegistrationIdentity:
        """Create an opaque identity for one exact live mutation."""

        return cls(
            surface=surface,
            registration_id=uuid4().hex,
            public_key=public_key,
        )


@dataclass(frozen=True)
class RegistrationDisposalResult:
    """Redacted outcome of attempting to remove one exact registration."""

    state: RegistrationDisposalState
    diagnostic_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in _DISPOSAL_STATES:
            raise ValueError(f"unsupported registration disposal state: {self.state}")
        if self.diagnostic_code is not None:
            _require_nonempty(
                self.diagnostic_code,
                name="registration disposal diagnostic code",
            )


RegistrationDisposer = Callable[
    [],
    None | RegistrationDisposalResult | Awaitable[None | RegistrationDisposalResult],
]


class RegistrationLease:
    """Capability token that removes only the registration that created it."""

    def __init__(
        self,
        *,
        owner: RegistrationOwner,
        identity: RegistrationIdentity,
        dispose: RegistrationDisposer,
    ) -> None:
        if not isinstance(owner, RegistrationOwner):
            raise TypeError("registration owner must be a RegistrationOwner")
        if not isinstance(identity, RegistrationIdentity):
            raise TypeError("registration identity must be a RegistrationIdentity")
        if not callable(dispose):
            raise TypeError("registration disposer must be callable")
        self._owner = owner
        self._identity = identity
        self._dispose = dispose
        self._state: RegistrationLeaseState = "active"
        self._last_result: RegistrationDisposalResult | None = None
        self._dispose_task: asyncio.Task[RegistrationDisposalResult] | None = None

    @property
    def owner(self) -> RegistrationOwner:
        return self._owner

    @property
    def identity(self) -> RegistrationIdentity:
        return self._identity

    @property
    def state(self) -> RegistrationLeaseState:
        return self._state

    @property
    def last_result(self) -> RegistrationDisposalResult | None:
        return self._last_result

    async def dispose(self) -> RegistrationDisposalResult:
        """Remove the exact entry once and join cleanup before cancellation wins."""

        if self._state == "disposed":
            return RegistrationDisposalResult(state="already_removed")
        if self._state == "failed_terminal":
            assert self._last_result is not None
            return self._last_result

        task = self._dispose_task
        if task is None:
            task = asyncio.create_task(self._dispose_once())
            self._dispose_task = task
        return await _await_cancellation_atomic(task)

    async def _dispose_once(self) -> RegistrationDisposalResult:
        self._state = "disposing"
        try:
            result = self._dispose()
            if inspect.isawaitable(result):
                result = await result
            if result is None:
                result = RegistrationDisposalResult(state="removed")
            elif not isinstance(result, RegistrationDisposalResult):
                raise TypeError(
                    "registration disposer must return a disposal result or None"
                )
        except asyncio.CancelledError:
            result = RegistrationDisposalResult(
                state="failed_retryable",
                diagnostic_code="registration_disposer_cancelled",
            )
        except Exception:
            result = RegistrationDisposalResult(
                state="failed_retryable",
                diagnostic_code="registration_disposer_failed",
            )

        self._last_result = result
        if result.state in {"removed", "already_removed"}:
            self._state = "disposed"
        elif result.state == "failed_retryable":
            self._state = "failed_retryable"
            self._dispose_task = None
        else:
            self._state = "failed_terminal"
        return result


@dataclass(frozen=True)
class RegistrationDisposalOutcome:
    """One identity-correlated result in a scope disposal report."""

    identity: RegistrationIdentity
    result: RegistrationDisposalResult


@dataclass(frozen=True)
class RegistrationScopeDisposalResult:
    """Ordered, redacted outcomes from one reverse-disposal pass."""

    outcomes: tuple[RegistrationDisposalOutcome, ...]

    @property
    def has_failures(self) -> bool:
        return any(
            outcome.result.state in {"failed_retryable", "failed_terminal"}
            for outcome in self.outcomes
        )


class RegistrationScope:
    """Collect one owner's leases and retire them in strict reverse order."""

    def __init__(self, owner: RegistrationOwner) -> None:
        if not isinstance(owner, RegistrationOwner):
            raise TypeError("registration scope owner must be a RegistrationOwner")
        self._owner = owner
        self._leases: list[RegistrationLease] = []
        self._state: RegistrationScopeState = "open"
        self._last_result: RegistrationScopeDisposalResult | None = None
        self._dispose_task: asyncio.Task[RegistrationScopeDisposalResult] | None = None

    @property
    def owner(self) -> RegistrationOwner:
        return self._owner

    @property
    def state(self) -> RegistrationScopeState:
        return self._state

    @property
    def last_result(self) -> RegistrationScopeDisposalResult | None:
        return self._last_result

    def add(self, lease: RegistrationLease) -> RegistrationLease:
        if self._state != "open":
            raise RuntimeError("registration scope no longer accepts leases")
        if not isinstance(lease, RegistrationLease):
            raise TypeError("registration scope accepts RegistrationLease values")
        if lease.owner != self._owner:
            raise ValueError("registration lease owner does not match scope owner")
        if lease.state != "active":
            raise ValueError("registration scope accepts only active leases")
        self._leases.append(lease)
        return lease

    def commit(self) -> None:
        if self._state != "open":
            raise RuntimeError("registration scope cannot be committed in this state")
        self._state = "committed"

    async def dispose(self) -> RegistrationScopeDisposalResult:
        if self._state in {"disposed", "failed_terminal"}:
            assert self._last_result is not None
            return self._last_result

        task = self._dispose_task
        if task is None:
            task = asyncio.create_task(self._dispose_all())
            self._dispose_task = task
        return await _await_cancellation_atomic(task)

    async def _dispose_all(self) -> RegistrationScopeDisposalResult:
        self._state = "disposing"
        outcomes: list[RegistrationDisposalOutcome] = []
        for lease in reversed(self._leases):
            result = await lease.dispose()
            outcomes.append(
                RegistrationDisposalOutcome(identity=lease.identity, result=result)
            )

        report = RegistrationScopeDisposalResult(outcomes=tuple(outcomes))
        self._last_result = report
        states = {outcome.result.state for outcome in outcomes}
        if "failed_retryable" in states:
            self._state = "failed_retryable"
            self._dispose_task = None
        elif "failed_terminal" in states:
            self._state = "failed_terminal"
        else:
            self._state = "disposed"
        return report

    async def __aenter__(self) -> RegistrationScope:
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._state == "open":
            await self.dispose()


T = TypeVar("T")


async def _await_cancellation_atomic(task: asyncio.Task[T]) -> T:
    """Join an owned cleanup task before propagating caller cancellation."""

    cancellation: asyncio.CancelledError | None = None
    caller = asyncio.current_task()
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            if caller is None or caller.cancelling() == 0:
                return task.result()
            cancellation = exc
    result = task.result()
    if cancellation is not None:
        raise cancellation
    return result


def _require_nonempty(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


__all__ = [
    "RegistrationDisposalOutcome",
    "RegistrationDisposalResult",
    "RegistrationIdentity",
    "RegistrationLease",
    "RegistrationOwner",
    "RegistrationScope",
    "RegistrationScopeDisposalResult",
]
