from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loushang.agent import AbortController, AbortSignal, Agent
from loushang.ai.types import AssistantMessage
from loushang.ai.utils import is_context_overflow
from loushang.coding.control import RetrySettings
from loushang.coding.event import AgentSessionEvent
from loushang.harness.host.retry import (
    RetryAttempt,
    RetryCoordinator,
    RetryOutcome,
    RetryPolicy,
)

_NON_RETRYABLE_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"requires an api key",
        r"\bapi[-_ ]?key\b",
        r"authorization",
        r"authentication",
        r"\bunauthorized\b",
        r"\bforbidden\b",
        r"\b401\b",
        r"\b403\b",
        r"access[_ -]?terminated",
        r"access.?denied",
        r"permission.?denied",
        r"currently only available",
    )
)


_RETRYABLE_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"overloaded",
        r"provider.?returned.?error",
        r"rate.?limit",
        r"too many requests",
        r"\b429\b",
        r"\b500\b",
        r"\b502\b",
        r"\b503\b",
        r"\b504\b",
        r"service.?unavailable",
        r"server.?error",
        r"internal.?error",
        r"network.?error",
        r"network.*connection.*lost",
        r"connection.?error",
        r"connection.?refused",
        r"connection.*lost",
        r"fetch failed",
        r"upstream.?connect",
        r"socket hang up",
        r"ended without",
        r"timed? out",
        r"timeout",
        r"terminated",
        r"retry delay",
    )
)


SettingsProvider = Callable[[], RetrySettings]
EventDispatcher = Callable[[AgentSessionEvent], Awaitable[None]]
ContinueRun = Callable[[], Awaitable[None]]
RuntimeExceptionRecorder = Callable[..., None]
RetrySleeper = Callable[[int, AbortSignal], Awaitable[None]]
WaitForIdle = Callable[[], Awaitable[None]]


@dataclass
class RetryController:
    agent: Agent
    get_settings: SettingsProvider
    dispatch_event: EventDispatcher
    continue_run: ContinueRun
    record_runtime_exception: RuntimeExceptionRecorder
    sleep_for_retry: RetrySleeper
    wait_for_idle: WaitForIdle | None = None
    _coordinator: RetryCoordinator[AbortController] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._coordinator = RetryCoordinator(
            create_cancel_handle=AbortController,
            cancel=lambda controller: controller.abort(),
            delay=lambda delay_ms, controller: self.sleep_for_retry(
                delay_ms, controller.signal
            ),
            continue_run=self.continue_run,
            on_started=self._on_started,
            on_finished=self._on_finished,
            wait_for_idle=self.wait_for_idle or self.agent.wait_for_idle,
        )

    @property
    def attempt(self) -> int:
        return self._coordinator.attempt

    @attempt.setter
    def attempt(self, value: int) -> None:
        self._coordinator.attempt = value

    @property
    def retry_future(self) -> asyncio.Future[None] | object | None:
        return self._coordinator.future

    @retry_future.setter
    def retry_future(self, value: asyncio.Future[None] | object | None) -> None:
        self._coordinator.future = value

    @property
    def is_retrying(self) -> bool:
        return self._coordinator.is_retrying

    @property
    def cancel_handle(self) -> AbortController | None:
        return self._coordinator.cancel_handle

    @cancel_handle.setter
    def cancel_handle(self, value: AbortController | None) -> None:
        self._coordinator.cancel_handle = value

    def abort(self) -> None:
        self._coordinator.abort()

    async def wait(self) -> None:
        await self._coordinator.wait()

    def ensure_future(self) -> asyncio.Future[None]:
        return self._coordinator.ensure_waiter()

    async def finish(
        self,
        *,
        success: bool,
        attempt: int,
        final_error: str | None = None,
    ) -> None:
        await self._coordinator.finish(
            RetryOutcome(
                success=success,
                attempt=attempt,
                error=final_error,
                cancelled=final_error == "Retry cancelled",
            )
        )

    async def finish_success_if_needed(
        self, assistant_message: AssistantMessage
    ) -> None:
        if assistant_message.stop_reason != "error" and self.attempt > 0:
            await self.finish(success=True, attempt=self.attempt)

    def should_prepare_retry(self, assistant_message: AssistantMessage) -> bool:
        settings = self.get_settings()
        return settings.enabled and self.is_retryable_error(assistant_message)

    def is_retryable_error(self, assistant_message: AssistantMessage) -> bool:
        if (
            assistant_message.stop_reason != "error"
            or not assistant_message.error_message
        ):
            return False
        context_window = self.agent.model.context_window or 0
        if is_context_overflow(assistant_message, context_window):
            return False
        if any(
            pattern.search(assistant_message.error_message)
            for pattern in _NON_RETRYABLE_ERROR_PATTERNS
        ):
            return False
        return any(
            pattern.search(assistant_message.error_message)
            for pattern in _RETRYABLE_ERROR_PATTERNS
        )

    async def handle_retryable_error(self, assistant_message: AssistantMessage) -> bool:
        settings = self.get_settings()
        return await self._coordinator.retry(
            assistant_message.error_message or "",
            policy=RetryPolicy(
                enabled=settings.enabled,
                max_attempts=settings.max_retries,
                base_delay_ms=settings.base_delay_ms,
            ),
            before_retry=self._remove_failed_assistant,
        )

    async def _on_started(self, attempt: RetryAttempt) -> None:
        await self.dispatch_event(
            {
                "type": "auto_retry_start",
                "attempt": attempt.attempt,
                "max_attempts": attempt.max_attempts,
                "delay_ms": attempt.delay_ms,
                "error_message": attempt.error,
            }
        )

    async def _on_finished(self, outcome: RetryOutcome) -> None:
        final_error = "Retry cancelled" if outcome.cancelled else outcome.error
        if final_error is not None:
            self.record_runtime_exception(
                code="retry_cancelled" if outcome.cancelled else "retry_failed",
                exc=final_error,
            )
            event: AgentSessionEvent = {
                "type": "auto_retry_end",
                "success": outcome.success,
                "attempt": outcome.attempt,
                "final_error": final_error,
            }
        else:
            event = {
                "type": "auto_retry_end",
                "success": outcome.success,
                "attempt": outcome.attempt,
            }
        await self.dispatch_event(event)

    def _remove_failed_assistant(self) -> None:
        if (
            self.agent.state.messages
            and getattr(self.agent.state.messages[-1], "role", None) == "assistant"
        ):
            self.agent.state.set_messages(self.agent.state.messages[:-1])
