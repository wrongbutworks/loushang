from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TextIO

from loushang.coding.event.presentation_policy import is_cancelled_error_message
from loushang.coding.ui.prompt_dispatch import PromptDispatchOutcome
from loushang.harnesstui.conversation.dispatch import (
    ConversationResultPresenter,
    ResultRenderer,
    StableEmit,
    TraceFn,
)

Renderer = ResultRenderer


class Lifecycle(Protocol):
    aborted_id: int | None

    def clear_aborted(self, run_id: int) -> None: ...


class PromptResultHandler:
    """Keep Coding cancellation policy around neutral result presentation."""

    def __init__(
        self,
        *,
        lifecycle: Lifecycle,
        renderer: Renderer,
        emit: StableEmit,
        stderr: TextIO,
        verbose: bool,
        last_error_message: Callable[[], str | None],
        session_error_message: Callable[[], str | None],
        now: Callable[[], float],
        trace: TraceFn,
    ) -> None:
        self._lifecycle = lifecycle
        self._renderer = renderer
        self._emit = emit
        self._stderr = stderr
        self._verbose = verbose
        self._last_error_message = last_error_message
        self._session_error_message = session_error_message
        self._now = now
        self._trace = trace
        self._presenter = ConversationResultPresenter(
            renderer=renderer,
            emit=emit,
            stderr=stderr,
            verbose=verbose,
            last_error_message=last_error_message,
            now=now,
            trace=trace,
        )

    async def handle(
        self,
        outcome: PromptDispatchOutcome,
        *,
        prompt_started: float,
    ) -> int | None:
        result = outcome.result
        run_id = outcome.run_id
        error_message = result.error_message or self._session_error_message()
        if (
            run_id is not None
            and self._lifecycle.aborted_id == run_id
            and is_cancelled_error_message(error_message)
        ):
            self._lifecycle.clear_aborted(run_id)
            self._trace(
                "prompt.suppressed_cancelled",
                run_id=run_id,
                error_message=error_message,
            )
            return result.exit_code

        return await self._presenter.handle(
            outcome,
            prompt_started=prompt_started,
            error_message=error_message,
        )


__all__ = ["PromptResultHandler"]
