from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loushang.coding.tools import ToolDefinitionResolver
from loushang.coding.ui.plain_renderer import PlainCodingUiRenderer, extract_text
from loushang.coding.ui.tool_blocks import ToolCallSnapshot, ToolTranscriptProjector


@dataclass
class CodingUiEventRenderer:
    renderer: PlainCodingUiRenderer
    tool_definition_resolver: ToolDefinitionResolver | None = None
    max_tool_body_lines: int = 8
    tool_calls: dict[str, ToolCallSnapshot] = field(default_factory=dict)
    rendered_tool_results: set[str] = field(default_factory=set)
    rendered_assistant_errors: set[int] = field(default_factory=set)
    last_error_message: str | None = None
    render_user_messages: bool = True
    _tool_projector: ToolTranscriptProjector = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._tool_projector = ToolTranscriptProjector(
            tool_definition_resolver=self.tool_definition_resolver,
            max_body_lines=self.max_tool_body_lines,
        )

    def handle(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "message_start":
            self._handle_message_start(event)
            return
        if event_type == "message_update":
            self._handle_message_update(event)
            return
        if event_type == "message_end":
            self._handle_message_end(event)
            return
        if event_type == "tool_execution_start":
            tool_call_id = str(event.get("tool_call_id") or event.get("tool_name") or "tool")
            self.tool_calls[tool_call_id] = self._tool_projector.remember_call(event)
            return
        if event_type == "tool_execution_update":
            return
        if event_type == "tool_execution_end":
            self._handle_tool_end(event)
            return
        if event_type == "agent_end":
            self._handle_agent_end(event)
            return
        if event_type == "auto_retry_start":
            self.renderer.render_status(
                "[retry] attempt "
                f"{event.get('attempt')}/{event.get('max_attempts')} "
                f"in {event.get('delay_ms')}ms: {event.get('error_message')}"
            )
            return
        if event_type == "compaction_start":
            self.renderer.render_status(f"[compact] start: {event.get('reason')}")
            return
        if event_type == "compaction_end":
            if event.get("error_message"):
                self.renderer.render_status(f"[compact] error: {event.get('error_message')}")
            else:
                self.renderer.render_status("[compact] done")
            return

    def _handle_message_start(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        role = getattr(message, "role", None)
        if role == "user" and self.render_user_messages:
            self.renderer.render_user(extract_text(message))
        elif role == "assistant":
            self.renderer.begin_assistant()

    def _handle_message_update(self, event: dict[str, Any]) -> None:
        assistant_event = event.get("assistant_message_event")
        if not isinstance(assistant_event, dict):
            return
        if assistant_event.get("type") == "text_delta":
            delta = assistant_event.get("delta")
            if isinstance(delta, str):
                self.renderer.write_assistant_delta(delta)

    def _handle_message_end(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        role = getattr(message, "role", None)
        if role == "assistant":
            if self._render_assistant_error(message):
                return
            self.renderer.end_assistant(extract_text(message))
        elif role == "toolResult":
            tool_call_id = str(getattr(message, "tool_call_id", "") or "")
            if tool_call_id and tool_call_id in self.rendered_tool_results:
                return
            if tool_call_id:
                self.rendered_tool_results.add(tool_call_id)
            self.renderer.render_tool_block(self._tool_projector.project_tool_result_message(message))

    def _handle_agent_end(self, event: dict[str, Any]) -> None:
        messages = event.get("messages")
        if not isinstance(messages, list):
            return
        for message in reversed(messages):
            if getattr(message, "role", None) == "assistant":
                self._render_assistant_error(message)
                return

    def _render_assistant_error(self, message: object) -> bool:
        error_message = getattr(message, "error_message", None)
        stop_reason = getattr(message, "stop_reason", None)
        if not isinstance(error_message, str) or not error_message:
            return False
        if stop_reason not in {"error", "aborted"}:
            return False
        if _is_intentional_abort_error(stop_reason, error_message):
            self.last_error_message = error_message
            return True
        message_id = id(message)
        if message_id in self.rendered_assistant_errors:
            return True
        self.rendered_assistant_errors.add(message_id)
        self.last_error_message = error_message
        self.renderer.render_error(error_message)
        return True

    def _handle_tool_end(self, event: dict[str, Any]) -> None:
        tool_call_id = str(event.get("tool_call_id") or event.get("tool_name") or "tool")
        snapshot = self.tool_calls.pop(tool_call_id, None)
        self.rendered_tool_results.add(tool_call_id)
        self.renderer.render_tool_block(self._tool_projector.project_result(event, snapshot))


def _is_intentional_abort_error(stop_reason: object, error_message: object) -> bool:
    if stop_reason != "aborted":
        return False
    if not isinstance(error_message, str):
        return True
    normalized = error_message.strip().lower()
    return normalized in {
        "request cancelled.",
        "request cancelled",
        "operation aborted",
        "request aborted by user",
    } or "aborted" in normalized


__all__ = ["CodingUiEventRenderer"]
