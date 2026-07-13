from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Generic, TypeVar, cast

P = TypeVar("P")
ScheduledCallback = Callable[[P], Awaitable[None] | None]
MergePending = Callable[[P, P], P]
_MISSING = object()


class CoalescingScheduler(Generic[P]):
    """Delay work, merge pending requests, and provide deterministic draining."""

    def __init__(
        self,
        callback: ScheduledCallback[P],
        *,
        merge: MergePending[P],
        delay_seconds: float = 0.0,
    ) -> None:
        self._callback = callback
        self._merge = merge
        self.delay_seconds = delay_seconds
        self._pending: P | object = _MISSING
        self._task: asyncio.Task[None] | None = None

    @property
    def is_pending(self) -> bool:
        return self._pending is not _MISSING

    def schedule(self, value: P) -> None:
        if self._pending is _MISSING:
            self._pending = value
        else:
            self._pending = self._merge(cast(P, self._pending), value)

        task = self._task
        if task is not None and not task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._run_without_loop()
            return
        self._task = loop.create_task(self._run_delayed())

    async def drain(self) -> None:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._task = None
        await self._run_pending()

    async def _run_delayed(self) -> None:
        task = asyncio.current_task()
        try:
            await asyncio.sleep(max(0.0, self.delay_seconds))
            await self._run_pending()
        finally:
            if self._task is task:
                self._task = None

    async def _run_pending(self) -> None:
        while self._pending is not _MISSING:
            value = self._take_pending()
            result = self._callback(value)
            if inspect.isawaitable(result):
                await result

    def _run_without_loop(self) -> None:
        while self._pending is not _MISSING:
            value = self._take_pending()
            result = self._callback(value)
            if inspect.isawaitable(result):
                asyncio.run(_await_result(result))

    def _take_pending(self) -> P:
        value = cast(P, self._pending)
        self._pending = _MISSING
        return value


async def _await_result(result: Awaitable[None]) -> None:
    await result


__all__ = ["CoalescingScheduler", "MergePending", "ScheduledCallback"]
