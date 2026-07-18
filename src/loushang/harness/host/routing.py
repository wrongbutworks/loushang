from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Generic, TypeVar

E = TypeVar("E")
RouteHandler = Callable[[E], bool | None | Awaitable[bool | None]]


class PayloadEventRouter(Generic[E]):
    """Route opaque events through ordered before, mirror, and after stages."""

    def __init__(
        self,
        *,
        kind_of: Callable[[E], str],
        before: Mapping[str, Sequence[RouteHandler[E]]] | None = None,
        mirrors: Sequence[RouteHandler[E]] = (),
        after: Mapping[str, Sequence[RouteHandler[E]]] | None = None,
    ) -> None:
        self._kind_of = kind_of
        self._before = {
            kind: tuple(handlers) for kind, handlers in (before or {}).items()
        }
        self._mirrors = tuple(mirrors)
        self._after = {
            kind: tuple(handlers) for kind, handlers in (after or {}).items()
        }

    async def route(self, event: E) -> bool:
        kind = self._kind_of(event)
        if await self._run(self._before.get(kind, ()), event):
            return True
        if await self._run(self._mirrors, event):
            return True
        return await self._run(self._after.get(kind, ()), event)

    @staticmethod
    async def _run(handlers: Sequence[RouteHandler[E]], event: E) -> bool:
        for handler in handlers:
            result = handler(event)
            if inspect.isawaitable(result):
                result = await result
            if result:
                return True
        return False


__all__ = ["PayloadEventRouter", "RouteHandler"]
