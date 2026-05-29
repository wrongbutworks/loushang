from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from loushang.agent import AbortSignal, AgentEvent
from loushang.ai.types import AssistantMessage
from loushang.coding.event import AgentSessionEvent


AppendMessage = Callable[[object], None]
EventDispatcher = Callable[[AgentSessionEvent], Awaitable[None]]
ExtensionEventEmitter = Callable[[AgentEvent], Awaitable[None]]
ToolExecutionErrorRecorder = Callable[[AgentEvent], None]
ExtensionDiagnosticsSync = Callable[..., None]
AssistantResponseErrorRecorder = Callable[[AssistantMessage], None]
AutoCompactionChecker = Callable[[AssistantMessage], Awaitable[object | None]]
UserMessageConsumer = Callable[[object], bool]


class RetryRouterPort(Protocol):
    async def finish_success_if_needed(self, assistant_message: AssistantMessage) -> None: ...

    def should_prepare_retry(self, assistant_message: AssistantMessage) -> bool: ...

    def ensure_future(self) -> object: ...

    def is_retryable_error(self, assistant_message: AssistantMessage) -> bool: ...

    async def handle_retryable_error(self, assistant_message: AssistantMessage) -> bool: ...


class CompactionRouterPort(Protocol):
    def clear_overflow_recovery_attempted(self) -> None: ...


@dataclass
class AgentEventRouter:
    append_message: AppendMessage
    dispatch_event: EventDispatcher
    emit_extension_agent_event: ExtensionEventEmitter
    record_tool_execution_error: ToolExecutionErrorRecorder
    retry_controller: RetryRouterPort
    compaction_controller: CompactionRouterPort
    sync_extension_diagnostics: ExtensionDiagnosticsSync
    record_assistant_response_error: AssistantResponseErrorRecorder
    check_auto_compaction: AutoCompactionChecker
    consume_user_message: UserMessageConsumer | None = None

    async def handle(self, event: AgentEvent, signal: AbortSignal) -> None:
        del signal
        if event["type"] == "message_start" and getattr(event["message"], "role", None) == "user":
            if self.consume_user_message is not None:
                self.consume_user_message(event["message"])
        if event["type"] == "message_end":
            self.append_message(event["message"])
        if event["type"] == "tool_execution_end" and event.get("is_error"):
            self.record_tool_execution_error(event)
        await self.dispatch_event(event)
        await self.emit_extension_agent_event(event)
        if event["type"] == "message_end" and getattr(event["message"], "role", None) == "assistant":
            assistant_message = event["message"]
            await self.retry_controller.finish_success_if_needed(assistant_message)
            if assistant_message.stop_reason != "error":
                self.compaction_controller.clear_overflow_recovery_attempted()
        if event["type"] == "agent_end":
            self.sync_extension_diagnostics(phase="runtime")
            last_assistant_message = _last_assistant_message(event["messages"])
            if last_assistant_message is not None:
                self.record_assistant_response_error(last_assistant_message)
                if self.retry_controller.should_prepare_retry(last_assistant_message):
                    self.retry_controller.ensure_future()
                if self.retry_controller.is_retryable_error(last_assistant_message):
                    did_retry = await self.retry_controller.handle_retryable_error(last_assistant_message)
                    if did_retry:
                        return
                await self.check_auto_compaction(last_assistant_message)


def _last_assistant_message(messages: list[object]) -> AssistantMessage | None:
    for message in reversed(messages):
        if isinstance(message, AssistantMessage):
            return message
    return None
