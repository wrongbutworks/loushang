"""Coding policy adapter for Harness-owned transcript retry runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loushang.agent import Agent
from loushang.ai.utils import is_context_overflow
from loushang.coding.control import RetrySettings
from loushang.harness.agent_transcript import AgentTranscriptRetryRuntime
from loushang.harness.events import SessionRuntimeEventPayload
from loushang.harness.host.retry import RetryPolicy
from loushang.harness.runtime import CancellationSignal

SettingsProvider = Callable[[], RetrySettings]
EventDispatcher = Callable[[SessionRuntimeEventPayload], Awaitable[None]]
ContinueRun = Callable[[], Awaitable[None]]
RuntimeExceptionRecorder = Callable[..., None]
RetrySleeper = Callable[[int, CancellationSignal], Awaitable[None]]
WaitForIdle = Callable[[], Awaitable[None]]


class RetryController(AgentTranscriptRetryRuntime):
    """Bind Coding settings and Agent state to the shared retry runtime."""

    def __init__(
        self,
        *,
        agent: Agent,
        get_settings: SettingsProvider,
        dispatch_event: EventDispatcher,
        continue_run: ContinueRun,
        record_runtime_exception: RuntimeExceptionRecorder,
        sleep_for_retry: RetrySleeper,
        wait_for_idle: WaitForIdle | None = None,
    ) -> None:
        super().__init__(
            get_policy=lambda: _retry_policy(get_settings()),
            get_messages=lambda: list(agent.state.messages),
            set_messages=agent.state.set_messages,
            get_context_window=lambda: agent.model.context_window,
            dispatch_event=dispatch_event,
            continue_run=continue_run,
            record_runtime_exception=record_runtime_exception,
            sleep_for_retry=sleep_for_retry,
            is_context_overflow_fn=is_context_overflow,
            wait_for_idle=wait_for_idle or agent.wait_for_idle,
        )


def _retry_policy(settings: RetrySettings) -> RetryPolicy:
    return RetryPolicy(
        enabled=settings.enabled,
        max_attempts=settings.max_retries,
        base_delay_ms=settings.base_delay_ms,
    )


__all__ = ["RetryController"]
