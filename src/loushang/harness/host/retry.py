from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

C = TypeVar("C")


@dataclass(frozen=True)
class RetryPolicy:
    enabled: bool
    max_attempts: int
    base_delay_ms: int
    backoff_factor: float = 2.0


@dataclass(frozen=True)
class RetryAttempt:
    attempt: int
    max_attempts: int
    delay_ms: int
    error: str


@dataclass(frozen=True)
class RetryOutcome:
    success: bool
    attempt: int
    error: str | None = None
    cancelled: bool = False


Delay = Callable[[int, C], Awaitable[None]]
Cancel = Callable[[C], None]
RetryStarted = Callable[[RetryAttempt], Awaitable[None]]
RetryFinished = Callable[[RetryOutcome], Awaitable[None]]
AsyncAction = Callable[[], Awaitable[None]]


class RetryCoordinator(Generic[C]):
    """Own retry attempt, backoff, cancellation, and waiter lifecycle."""

    def __init__(
        self,
        *,
        create_cancel_handle: Callable[[], C],
        cancel: Cancel[C],
        delay: Delay[C],
        continue_run: AsyncAction,
        on_started: RetryStarted,
        on_finished: RetryFinished,
        wait_for_idle: AsyncAction | None = None,
    ) -> None:
        self._create_cancel_handle = create_cancel_handle
        self._cancel = cancel
        self._delay = delay
        self._continue_run = continue_run
        self._on_started = on_started
        self._on_finished = on_finished
        self._wait_for_idle = wait_for_idle
        self._attempt = 0
        self._future: asyncio.Future[None] | object | None = None
        self._cancel_handle: C | None = None
        self._delay_active = False

    @property
    def attempt(self) -> int:
        return self._attempt

    @attempt.setter
    def attempt(self, value: int) -> None:
        self._attempt = value

    @property
    def future(self) -> asyncio.Future[None] | object | None:
        return self._future

    @future.setter
    def future(self, value: asyncio.Future[None] | object | None) -> None:
        self._future = value

    @property
    def cancel_handle(self) -> C | None:
        return self._cancel_handle

    @cancel_handle.setter
    def cancel_handle(self, value: C | None) -> None:
        self._cancel_handle = value

    @property
    def is_retrying(self) -> bool:
        return self._future is not None

    def ensure_waiter(self) -> asyncio.Future[None]:
        if not isinstance(self._future, asyncio.Future):
            self._future = asyncio.get_running_loop().create_future()
        return self._future

    def abort(self) -> None:
        if self._cancel_handle is not None:
            self._cancel(self._cancel_handle)

    async def wait(self) -> None:
        future = self._future
        if future is None:
            return
        if isinstance(future, asyncio.Future):
            await future
        if self._wait_for_idle is not None:
            await self._wait_for_idle()

    async def finish(self, outcome: RetryOutcome) -> None:
        try:
            await self._on_finished(outcome)
        finally:
            self._resolve_and_reset()

    async def retry(
        self,
        error: str,
        *,
        policy: RetryPolicy,
        before_retry: Callable[[], None] | None = None,
    ) -> bool:
        if not policy.enabled:
            if self._future is not None:
                await self.finish(
                    RetryOutcome(success=False, attempt=self._attempt, error=error)
                )
            return False
        if self._delay_active:
            raise RuntimeError("Retry delay already in progress")

        self.ensure_waiter()
        self._attempt += 1
        if self._attempt > max(0, policy.max_attempts):
            await self.finish(
                RetryOutcome(
                    success=False,
                    attempt=self._attempt - 1,
                    error=error,
                )
            )
            return False

        delay_ms = _backoff_delay(policy, self._attempt)
        attempt = RetryAttempt(
            attempt=self._attempt,
            max_attempts=policy.max_attempts,
            delay_ms=delay_ms,
            error=error,
        )
        try:
            await self._on_started(attempt)
            if before_retry is not None:
                before_retry()

            cancel_handle = self._create_cancel_handle()
            self._cancel_handle = cancel_handle
            self._delay_active = True
            await self._delay(delay_ms, cancel_handle)
        except asyncio.CancelledError:
            await self.finish(
                RetryOutcome(
                    success=False,
                    attempt=self._attempt,
                    cancelled=True,
                )
            )
            return False
        except BaseException:
            self._resolve_and_reset()
            raise
        finally:
            self._delay_active = False

        asyncio.ensure_future(self._continue_run())
        return True

    def _resolve_and_reset(self) -> None:
        future = self._future
        if isinstance(future, asyncio.Future) and not future.done():
            future.set_result(None)
        self._future = None
        self._cancel_handle = None
        self._attempt = 0
        self._delay_active = False


def _backoff_delay(policy: RetryPolicy, attempt: int) -> int:
    delay = max(0, policy.base_delay_ms) * policy.backoff_factor ** max(0, attempt - 1)
    return max(0, int(delay))


__all__ = [
    "RetryAttempt",
    "RetryCoordinator",
    "RetryOutcome",
    "RetryPolicy",
]
