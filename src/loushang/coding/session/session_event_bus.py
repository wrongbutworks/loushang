from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable

from loushang.coding.event import AgentSessionEvent

SessionEventListener = Callable[[AgentSessionEvent], Awaitable[None] | None]


class SessionEventBus:
    def __init__(self) -> None:
        self._listeners: list[SessionEventListener] = []
        self._event_queue: asyncio.Task[None] | None = None

    def subscribe(self, listener: SessionEventListener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def clear(self) -> None:
        self._listeners.clear()

    async def dispatch(self, event: AgentSessionEvent) -> None:
        task = self.schedule(event)
        await task

    def schedule(self, event: AgentSessionEvent) -> asyncio.Task[None]:
        loop = asyncio.get_running_loop()
        previous = self._event_queue

        async def runner() -> None:
            if previous is not None:
                try:
                    await previous
                except Exception:
                    pass
            for listener in list(self._listeners):
                await _await_listener(listener, event)

        task = loop.create_task(runner())
        self._event_queue = task
        return task

    def dispatch_without_loop(self, event: AgentSessionEvent) -> None:
        for listener in list(self._listeners):
            result = listener(event)
            if inspect.isawaitable(result):
                close = getattr(result, "close", None)
                if callable(close):
                    close()
                raise RuntimeError("Async session listeners require a running event loop.")


async def _await_listener(listener: SessionEventListener, event: AgentSessionEvent) -> None:
    result = listener(event)
    if inspect.isawaitable(result):
        await result
