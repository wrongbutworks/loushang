from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.tool_blocks import (
    ToolCallSnapshot,
    ToolTranscriptBlock,
    ToolTranscriptProjector,
)
from loushang.coding.ui.transcript_projection import tool_block_to_record
from loushang.tui.transcript import ToolExecutionRecord

QueueReader = Callable[[], tuple[str, ...] | list[str]]
TraceFn = Callable[[str], None]


@dataclass(slots=True)
class ScreenCodingEventProjector:
    app: ScreenCodingTuiApp
    tool_definition_resolver: Any | None = None
    max_tool_body_lines: int = 8
    read_pending_steers: QueueReader = tuple
    read_pending_followups: QueueReader = tuple
    now: Callable[[], float] = time.monotonic
    _tool_projector: ToolTranscriptProjector = field(init=False, repr=False)
    _tool_calls: dict[str, ToolCallSnapshot] = field(default_factory=dict, init=False, repr=False)
    _tool_started_at: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._tool_projector = ToolTranscriptProjector(
            tool_definition_resolver=self.tool_definition_resolver,
            max_body_lines=self.max_tool_body_lines,
        )

    def handle(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "agent_start":
            self._handle_agent_start()
            return
        if event_type == "queue_update":
            self._sync_queues()
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
        if event_type == "tool_execution_start":
            self._handle_tool_start(event)
            return
        if event_type == "tool_execution_update":
            self._handle_tool_update(event)
            return
        if event_type == "tool_execution_end":
            self._handle_tool_end(event)
            return
        if event_type == "auto_retry_start":
            self.app.set_status(
                "retry "
                f"{event.get('attempt')}/{event.get('max_attempts')} "
                f"in {event.get('delay_ms')}ms: {event.get('error_message')}"
            )
            return
        if event_type == "compaction_start":
            self.app.set_status(f"compact start: {event.get('reason')}")
            return
        if event_type == "compaction_end":
            if event.get("error_message"):
                self.app.set_status(f"compact error: {event.get('error_message')}")
            else:
                self.app.set_status("compact done")
                summary = _compaction_summary(event)
                if summary:
                    self.app.append_context_compaction_record(
                        summary=summary,
                        tokens_before=_compaction_tokens_before(event),
                    )

    def _handle_agent_start(self) -> None:
        self._tool_calls.clear()
        self._tool_started_at.clear()
        if not self.app.state.running:
            self.app.begin_run(started_at=self.now())

    def _sync_queues(self) -> None:
        self.app.sync_queues(
            steers=tuple(self.read_pending_steers()),
            followups=tuple(self.read_pending_followups()),
        )

    def _handle_message_start(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        role = getattr(message, "role", None)
        if role == "user":
            text = _extract_text(message).strip()
            if text and not self.app.state.consume_pending_user_echo(text):
                self.app.state.records.append(_user_record(text))
            return
        if role == "assistant":
            self.app.begin_assistant()

    def _handle_message_update(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        if getattr(message, "role", None) != "assistant":
            return
        assistant_event = event.get("assistant_message_event")
        if not isinstance(assistant_event, dict):
            return
        if assistant_event.get("type") != "text_delta":
            return
        delta = assistant_event.get("delta")
        if isinstance(delta, str):
            self.app.append_assistant_chunk(delta)

    def _handle_message_end(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        role = getattr(message, "role", None)
        if role == "assistant":
            text = _extract_text(message)
            stop_reason = getattr(message, "stop_reason", None)
            error_message = getattr(message, "error_message", None)
            self.app.end_assistant(text)
            if stop_reason in {"error", "aborted"} and isinstance(error_message, str) and error_message:
                self.app.add_error(error_message)

    def _handle_tool_start(self, event: dict[str, Any]) -> None:
        tool_call_id = _tool_call_id(event)
        snapshot = self._tool_projector.remember_call(event)
        self._tool_calls[tool_call_id] = snapshot
        self._tool_started_at[tool_call_id] = self.now()
        self.app.state.upsert_tool_record(
            tool_call_id,
            ToolExecutionRecord(
                name=_tool_title(snapshot, event),
                state="running",
                elapsed_seconds=0.0,
            ),
        )

    def _handle_tool_update(self, event: dict[str, Any]) -> None:
        tool_call_id = _tool_call_id(event)
        if tool_call_id not in self._tool_calls:
            self._handle_tool_start(event)

    def _handle_tool_end(self, event: dict[str, Any]) -> None:
        tool_call_id = _tool_call_id(event)
        snapshot = self._tool_calls.get(tool_call_id)
        started_at = self._tool_started_at.get(tool_call_id, self.now())
        block = self._tool_projector.project_result(event, snapshot)
        self.app.state.upsert_tool_record(
            tool_call_id,
            tool_block_to_record(block, elapsed_seconds=max(0.0, self.now() - started_at)),
        )
        self._tool_calls.pop(tool_call_id, None)
        self._tool_started_at.pop(tool_call_id, None)


def _tool_call_id(event: dict[str, Any]) -> str:
    value = event.get("tool_call_id", event.get("toolCallId"))
    if isinstance(value, str) and value:
        return value
    value = event.get("tool_name", event.get("toolName"))
    return value if isinstance(value, str) and value else "tool"


def _tool_title(snapshot: ToolCallSnapshot, event: dict[str, Any]) -> str:
    if snapshot.rendered_call_text:
        return snapshot.rendered_call_text.splitlines()[0].strip()
    block = ToolTranscriptBlock(
        tool_call_id=_tool_call_id(event),
        tool_name=snapshot.tool_name,
        status="running",
        verb="Ran",
        title=snapshot.tool_name,
    )
    return tool_block_to_record(block).name


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


def _user_record(text: str):
    from loushang.tui.transcript import UserPromptRecord

    return UserPromptRecord(text)


__all__ = ["ScreenCodingEventProjector"]
