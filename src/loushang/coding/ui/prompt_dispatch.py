from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from loushang.coding.ui.controller import ControllerResult
from loushang.coding.ui.intent import BashIntent, CodingUiIntent, PromptIntent


class Lifecycle(Protocol):
    active: bool

    def begin_work(self) -> int: ...
    def end_work(self) -> None: ...


class Controller(Protocol):
    async def dispatch(self, intent: CodingUiIntent) -> ControllerResult: ...


class TraceFn(Protocol):
    def __call__(self, name: str, **data: Any) -> None: ...


@dataclass(frozen=True)
class PromptDispatchOutcome:
    result: ControllerResult
    run_id: int | None
    work_intent: bool
    started_at: float


class PromptDispatchHandler:
    def __init__(
        self,
        *,
        lifecycle: Lifecycle,
        controller: Controller,
        session_running: Any,
        now: Callable[[], float] = time.monotonic,
        trace: TraceFn,
    ) -> None:
        self._lifecycle = lifecycle
        self._controller = controller
        self._session_running = session_running
        self._now = now
        self._trace = trace

    async def dispatch(self, intent: CodingUiIntent) -> PromptDispatchOutcome:
        work_intent = isinstance(intent, PromptIntent | BashIntent)
        started_at = self._now()
        run_id: int | None = None
        if work_intent:
            run_id = self._lifecycle.begin_work()
        self._trace(
            "prompt.dispatch.start",
            intent=type(intent).__name__,
            work_intent=work_intent,
            run_id=run_id,
        )
        try:
            result = await self._controller.dispatch(intent)
        finally:
            if work_intent:
                self._lifecycle.end_work()
            self._trace(
                "prompt.dispatch.end",
                run_id=run_id,
                active_run=self._lifecycle.active,
                session_running=bool(self._session_running()),
            )
        return PromptDispatchOutcome(result=result, run_id=run_id, work_intent=work_intent, started_at=started_at)


__all__ = ["PromptDispatchHandler", "PromptDispatchOutcome"]
