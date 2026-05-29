from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loushang.agent import AbortController, AbortSignal, Agent
from loushang.ai import is_context_overflow
from loushang.ai.types import AssistantMessage
from loushang.coding.control import RetrySettings
from loushang.coding.event import AgentSessionEvent

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


@dataclass
class RetryController:
    agent: Agent
    get_settings: SettingsProvider
    dispatch_event: EventDispatcher
    continue_run: ContinueRun
    record_runtime_exception: RuntimeExceptionRecorder
    sleep_for_retry: RetrySleeper
    _retry_attempt: int = 0
    _retry_future: asyncio.Future[None] | object | None = None
    _retry_abort_controller: AbortController | None = None

    @property
    def attempt(self) -> int:
        return self._retry_attempt

    @property
    def retry_future(self) -> asyncio.Future[None] | object | None:
        return self._retry_future

    @retry_future.setter
    def retry_future(self, value: asyncio.Future[None] | object | None) -> None:
        self._retry_future = value

    @property
    def is_retrying(self) -> bool:
        return self._retry_future is not None

    def abort(self) -> None:
        if self._retry_abort_controller is not None:
            self._retry_abort_controller.abort()

    async def wait(self) -> None:
        retry_future = self._retry_future
        if retry_future is None:
            return
        if isinstance(retry_future, asyncio.Future):
            await retry_future
        await self.agent.wait_for_idle()

    def ensure_future(self) -> asyncio.Future[None]:
        if not isinstance(self._retry_future, asyncio.Future):
            self._retry_future = asyncio.get_running_loop().create_future()
        return self._retry_future

    async def finish(
        self,
        *,
        success: bool,
        attempt: int,
        final_error: str | None = None,
    ) -> None:
        event: AgentSessionEvent = {
            "type": "auto_retry_end",
            "success": success,
            "attempt": attempt,
        }
        if final_error is not None:
            event["final_error"] = final_error
            self.record_runtime_exception(
                code="retry_cancelled" if final_error == "Retry cancelled" else "retry_failed",
                exc=final_error,
            )
        await self.dispatch_event(event)
        retry_future = self._retry_future
        if isinstance(retry_future, asyncio.Future) and not retry_future.done():
            retry_future.set_result(None)
        self._retry_future = None
        self._retry_abort_controller = None
        self._retry_attempt = 0

    async def finish_success_if_needed(self, assistant_message: AssistantMessage) -> None:
        if assistant_message.stop_reason != "error" and self._retry_attempt > 0:
            await self.finish(success=True, attempt=self._retry_attempt)

    def should_prepare_retry(self, assistant_message: AssistantMessage) -> bool:
        settings = self.get_settings()
        return settings.enabled and self.is_retryable_error(assistant_message)

    def is_retryable_error(self, assistant_message: AssistantMessage) -> bool:
        if assistant_message.stop_reason != "error" or not assistant_message.error_message:
            return False
        context_window = self.agent.model.context_window or 0
        if is_context_overflow(assistant_message, context_window):
            return False
        if any(pattern.search(assistant_message.error_message) for pattern in _NON_RETRYABLE_ERROR_PATTERNS):
            return False
        return any(pattern.search(assistant_message.error_message) for pattern in _RETRYABLE_ERROR_PATTERNS)

    async def handle_retryable_error(self, assistant_message: AssistantMessage) -> bool:
        settings = self.get_settings()
        if not settings.enabled:
            if self._retry_future is not None:
                await self.finish(
                    success=False,
                    attempt=self._retry_attempt,
                    final_error=assistant_message.error_message,
                )
            return False

        self.ensure_future()
        self._retry_attempt += 1
        if self._retry_attempt > settings.max_retries:
            await self.finish(
                success=False,
                attempt=self._retry_attempt - 1,
                final_error=assistant_message.error_message,
            )
            return False

        delay_ms = settings.base_delay_ms * 2 ** (self._retry_attempt - 1)
        await self.dispatch_event(
            {
                "type": "auto_retry_start",
                "attempt": self._retry_attempt,
                "max_attempts": settings.max_retries,
                "delay_ms": delay_ms,
                "error_message": assistant_message.error_message,
            }
        )
        if self.agent.state.messages and getattr(self.agent.state.messages[-1], "role", None) == "assistant":
            self.agent.state.set_messages(self.agent.state.messages[:-1])

        self._retry_abort_controller = AbortController()
        try:
            await self.sleep_for_retry(delay_ms, self._retry_abort_controller.signal)
        except asyncio.CancelledError:
            attempt = self._retry_attempt
            await self.finish(success=False, attempt=attempt, final_error="Retry cancelled")
            return False

        asyncio.create_task(self.continue_run())
        return True
