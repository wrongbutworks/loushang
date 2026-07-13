from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Generic, TypeVar

S = TypeVar("S")
SessionCallback = Callable[[S], Awaitable[None] | None]
LifecycleCallback = Callable[[], Awaitable[None] | None]


class SessionTransitionHost(Generic[S]):
    """Serialize replacement and own the active product session slot."""

    def __init__(
        self,
        current: S | None = None,
        *,
        dispose: SessionCallback[S],
        rebind: SessionCallback[S] | None = None,
        before_invalidate: LifecycleCallback | None = None,
    ) -> None:
        self._current = current
        self._dispose = dispose
        self._rebind = rebind
        self._before_invalidate = before_invalidate
        self._lock = asyncio.Lock()
        self._lock_owner: asyncio.Task[object] | None = None
        self._lock_depth = 0

    @property
    def current(self) -> S | None:
        return self._current

    def set_rebind(self, callback: SessionCallback[S] | None) -> None:
        self._rebind = callback

    def set_before_invalidate(
        self, callback: LifecycleCallback | None
    ) -> None:
        self._before_invalidate = callback

    @asynccontextmanager
    async def transition(self) -> AsyncIterator[None]:
        task = asyncio.current_task()
        if task is not None and self._lock_owner is task:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return

        await self._lock.acquire()
        self._lock_owner = task
        self._lock_depth = 1
        try:
            yield
        finally:
            self._lock_depth -= 1
            if self._lock_depth == 0:
                self._lock_owner = None
                self._lock.release()

    async def replace(
        self,
        next_session: S,
        *,
        prepare: SessionCallback[S] | None = None,
        before_release: SessionCallback[S] | None = None,
        activate: SessionCallback[S] | None = None,
    ) -> S:
        async with self.transition():
            if prepare is not None:
                await _invoke_session_callback(prepare, next_session)

            previous = self._current
            if previous is not None and previous is not next_session:
                await self._release(previous, before_release=before_release)
                self._current = None

            self._current = next_session
            if activate is not None:
                await _invoke_session_callback(activate, next_session)
            if self._rebind is not None:
                await _invoke_session_callback(self._rebind, next_session)
            return next_session

    async def dispose_current(
        self,
        *,
        before_release: SessionCallback[S] | None = None,
    ) -> None:
        async with self.transition():
            current = self._current
            if current is None:
                return
            await self._release(current, before_release=before_release)
            self._current = None

    async def _release(
        self,
        session: S,
        *,
        before_release: SessionCallback[S] | None,
    ) -> None:
        if before_release is not None:
            await _invoke_session_callback(before_release, session)
        if self._before_invalidate is not None:
            await _invoke_lifecycle_callback(self._before_invalidate)
        await _invoke_session_callback(self._dispose, session)


async def _invoke_session_callback(
    callback: SessionCallback[S], session: S
) -> None:
    result = callback(session)
    if inspect.isawaitable(result):
        await result


async def _invoke_lifecycle_callback(callback: LifecycleCallback) -> None:
    result = callback()
    if inspect.isawaitable(result):
        await result


__all__ = ["LifecycleCallback", "SessionCallback", "SessionTransitionHost"]
