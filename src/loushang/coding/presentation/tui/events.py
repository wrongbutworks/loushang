from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loushang.coding.event.presentation_policy import is_cancelled_error_message
from loushang.coding.presentation.tui.tool_transcript import (
    CodingToolTranscriptProjection,
)
from loushang.harnesstui.conversation.projection import ConversationProjector

QueueReader = Callable[[], tuple[str, ...] | list[str]]


@dataclass(slots=True)
class CodingConversationEventAdapter:
    """Translate raw Coding events into product-neutral conversation facts."""

    projector: ConversationProjector
    tool_projector: CodingToolTranscriptProjection
    read_pending_steers: QueueReader = tuple
    read_pending_followups: QueueReader = tuple
    recover_tool_updates: bool = True
    project_tool_result_messages: bool = True
    require_assistant_message_for_delta: bool = True
    project_run_starts: bool = True
    project_queue_updates: bool = True
    project_user_messages: bool = True
    project_assistant_error_text: bool = True
    project_compaction_details: bool = True

    def handle(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "agent_start":
            if self.project_run_starts:
                self.projector.run_started()
            return
        if event_type == "queue_update":
            if self.project_queue_updates:
                self.projector.queues_updated(
                    steers=tuple(self.read_pending_steers()),
                    followups=tuple(self.read_pending_followups()),
                )
            return
        if event_type == "message_start":
            self._handle_message_start(event)
            return
        if event_type == "message_update":
            self._handle_message_update(event)
            return
        if event_type == "message_end":
            self._handle_message_end(event)
            return
        if event_type == "agent_end":
            self._handle_agent_end(event)
            return
        if event_type == "tool_execution_start":
            self.projector.tool_started(self.tool_projector.call_view(event))
            return
        if event_type == "tool_execution_update":
            self._handle_tool_update(event)
            return
        if event_type == "tool_execution_end":
            tool_call_id = self.tool_projector.call_id(event)
            context = self.projector.begin_tool_finish(tool_call_id)
            self.projector.tool_finished(
                self.tool_projector.result_view(event, snapshot=context.snapshot),
                context=context,
            )
            return
        if event_type == "auto_retry_start":
            self.projector.retry_started(
                attempt=event.get("attempt"),
                max_attempts=event.get("max_attempts"),
                delay_ms=event.get("delay_ms"),
                error_message=event.get("error_message"),
            )
            return
        if event_type == "compaction_start":
            self.projector.compaction_started(reason=event.get("reason"))
            return
        if event_type == "compaction_end":
            self._handle_compaction_end(event)

    def _handle_message_start(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        role = getattr(message, "role", None)
        if role == "user":
            if self.project_user_messages:
                self.projector.user_message(_extract_text(message))
        elif role == "assistant":
            self.projector.assistant_started()

    def _handle_message_update(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        if (
            self.require_assistant_message_for_delta
            and getattr(message, "role", None) != "assistant"
        ):
            return
        assistant_event = event.get("assistant_message_event")
        if not isinstance(assistant_event, dict):
            return
        if assistant_event.get("type") != "text_delta":
            return
        delta = assistant_event.get("delta")
        if isinstance(delta, str):
            self.projector.assistant_delta(delta)

    def _handle_message_end(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        role = getattr(message, "role", None)
        if role == "assistant":
            error_message, show_error = _assistant_error(message)
            final_text = (
                ""
                if error_message is not None
                and not self.project_assistant_error_text
                else _extract_text(message)
            )
            self.projector.assistant_finished(
                final_text,
                error_message=error_message,
                show_error=show_error,
                error_id=id(message),
            )
            return
        if role == "toolResult" and self.project_tool_result_messages:
            tool_call_id = self.tool_projector.message_id(message)
            if tool_call_id and self.projector.has_rendered_tool_result(tool_call_id):
                return
            self.projector.tool_result_message(
                self.tool_projector.tool_result_message_view(message),
                deduplicate=bool(tool_call_id),
            )

    def _handle_tool_update(self, event: dict[str, Any]) -> None:
        if not self.recover_tool_updates:
            return
        tool_call_id = self.tool_projector.call_id(event)
        if self.projector.has_active_tool_call(tool_call_id):
            return
        self.projector.tool_updated(self.tool_projector.call_view(event))

    def _handle_compaction_end(self, event: dict[str, Any]) -> None:
        raw_error = event.get("error_message")
        if raw_error:
            self.projector.compaction_finished(
                error_message=(
                    raw_error if isinstance(raw_error, str) else str(raw_error)
                ),
                summary="",
                tokens_before=None,
            )
            return
        if not self.project_compaction_details:
            self.projector.compaction_finished(
                error_message=None,
                summary="",
                tokens_before=None,
            )
            return
        self.projector.compaction_finished(
            error_message=None,
            summary=_compaction_summary(event),
            tokens_before=_compaction_tokens_before(event),
        )

    def _handle_agent_end(self, event: dict[str, Any]) -> None:
        messages = event.get("messages")
        if not isinstance(messages, list):
            return
        for message in reversed(messages):
            if getattr(message, "role", None) != "assistant":
                continue
            error_message, show_error = _assistant_error(message)
            if error_message is not None:
                self.projector.assistant_error(
                    error_message,
                    show_error=show_error,
                    error_id=id(message),
                )
            return


def _assistant_error(message: object) -> tuple[str | None, bool]:
    error_message = getattr(message, "error_message", None)
    stop_reason = getattr(message, "stop_reason", None)
    if not isinstance(error_message, str) or not error_message:
        return None, False
    if stop_reason not in {"error", "aborted"}:
        return None, False
    show_error = not (
        stop_reason == "aborted" and is_cancelled_error_message(error_message)
    )
    return error_message, show_error


def _extract_text(value: object) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


def _compaction_summary(event: dict[str, Any]) -> str:
    result = event.get("result")
    if not isinstance(result, dict):
        return ""
    summary = result.get("summary")
    return summary.strip() if isinstance(summary, str) else ""


def _compaction_tokens_before(event: dict[str, Any]) -> int | None:
    result = event.get("result")
    if not isinstance(result, dict):
        return None
    tokens_before = result.get("tokens_before")
    return tokens_before if isinstance(tokens_before, int) else None


__all__ = ["CodingConversationEventAdapter", "QueueReader"]
