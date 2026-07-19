from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from loushang.coding.interaction.controller import ControllerResult
from loushang.coding.interaction.intent import BashIntent, CodingUiIntent, PromptIntent
from loushang.harnesstui.conversation.dispatch import (
    ConversationDispatchHandler,
    ConversationDispatchOutcome,
    DispatchLifecycle,
    TraceFn,
)

Lifecycle = DispatchLifecycle
PromptDispatchOutcome = ConversationDispatchOutcome


class Controller(Protocol):
    async def dispatch(self, intent: CodingUiIntent) -> ControllerResult: ...


class PromptDispatchHandler(ConversationDispatchHandler[CodingUiIntent]):
    """Adapt Coding intent classification to neutral dispatch coordination."""

    def __init__(
        self,
        *,
        lifecycle: Lifecycle,
        controller: Controller,
        session_running: Callable[[], object],
        now: Callable[[], float] = time.monotonic,
        trace: TraceFn,
    ) -> None:
        super().__init__(
            lifecycle=lifecycle,
            controller=controller,
            is_work_intent=_is_work_intent,
            session_running=session_running,
            now=now,
            trace=trace,
        )


def _is_work_intent(intent: CodingUiIntent) -> bool:
    return isinstance(intent, PromptIntent | BashIntent)


__all__ = ["PromptDispatchHandler", "PromptDispatchOutcome"]
