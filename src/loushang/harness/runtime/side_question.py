"""Product-neutral contracts for one-shot side questions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, cast

SideQuestionUpdate = Callable[[str], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class SideQuestionAnswer:
    """One transient answer produced outside the active conversation."""

    text: str
    context_revision: str | None = None
    usage: object | None = None


class SideQuestionProvider(Protocol):
    """Execute one question against an immutable Product context snapshot."""

    async def ask(
        self,
        question: str,
        *,
        on_update: SideQuestionUpdate | None = None,
    ) -> SideQuestionAnswer: ...

    def cancel(self) -> None: ...


class SideQuestionProviderFactory(Protocol):
    """Bind a selected side-question implementation to one live session."""

    def bind(self, context: object) -> SideQuestionProvider: ...


@dataclass(frozen=True, slots=True)
class SessionSideQuestionProviderFactory:
    """Delegate concrete Provider creation back to the bound Product session."""

    def bind(self, context: object) -> SideQuestionProvider:
        create = getattr(context, "create_side_question_provider", None)
        if not callable(create):
            raise TypeError(
                "Side-question capability requires a Product session Provider factory."
            )
        provider = create()
        if not callable(getattr(provider, "ask", None)) or not callable(
            getattr(provider, "cancel", None)
        ):
            raise TypeError(
                "Product session returned an invalid side-question Provider."
            )
        return cast(SideQuestionProvider, provider)


class SideQuestionCoordinator:
    """Own the single active side question for one session."""

    def __init__(self, provider: SideQuestionProvider) -> None:
        self._provider = provider
        self._active_task: asyncio.Task[object] | None = None

    @property
    def active(self) -> bool:
        task = self._active_task
        return task is not None and not task.done()

    async def ask(
        self,
        question: str,
        *,
        on_update: SideQuestionUpdate | None = None,
    ) -> SideQuestionAnswer:
        normalized = question.strip()
        if not normalized:
            raise ValueError("Side question must not be empty.")
        if self.active:
            raise RuntimeError("A side question is already running.")
        task = asyncio.current_task()
        if task is None:  # pragma: no cover - an async function always has a task here
            raise RuntimeError("Side question requires an active event loop task.")
        self._active_task = task
        try:
            return await self._provider.ask(normalized, on_update=on_update)
        finally:
            if self._active_task is task:
                self._active_task = None

    def cancel(self) -> bool:
        task = self._active_task
        if task is None or task.done():
            return False
        self._provider.cancel()
        task.cancel()
        return True


__all__ = [
    "SideQuestionAnswer",
    "SideQuestionCoordinator",
    "SideQuestionProvider",
    "SideQuestionProviderFactory",
    "SideQuestionUpdate",
    "SessionSideQuestionProviderFactory",
]
