from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Generic, TypeVar

T = TypeVar("T")
EventListener = Callable[[T], Awaitable[None] | None]


class OrderedEventBus(Generic[T]):
    def __init__(
        self,
        *,
        async_listener_error: str = "Async event listeners require a running event loop.",
    ) -> None:
        self._listeners: list[EventListener[T]] = []
        self._event_queue: asyncio.Task[None] | None = None
        self._async_listener_error = async_listener_error

    @property
    def has_listeners(self) -> bool:
        return bool(self._listeners)

    def subscribe(self, listener: EventListener[T]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def clear(self) -> None:
        self._listeners.clear()

    async def dispatch(self, event: T) -> None:
        await self.schedule(event)

    def schedule(self, event: T) -> asyncio.Task[None]:
        loop = asyncio.get_running_loop()
        previous = self._event_queue

        async def runner() -> None:
            if previous is not None:
                with suppress(Exception):
                    await previous
            for listener in list(self._listeners):
                result = listener(event)
                if inspect.isawaitable(result):
                    await result

        task = loop.create_task(runner())
        self._event_queue = task
        return task

    async def drain(self) -> None:
        task = self._event_queue
        if task is not None:
            await task

    def dispatch_without_loop(self, event: T) -> None:
        for listener in list(self._listeners):
            result = listener(event)
            if inspect.isawaitable(result):
                close = getattr(result, "close", None)
                if callable(close):
                    close()
                raise RuntimeError(self._async_listener_error)
