from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from loushang.agent.json_codec import serialize_tool_result
from loushang.ai.json_codec import serialize_assistant_message_event
from loushang.harness.agent_transcript import create_agent_transcript_message_codec
from loushang.harness.context import serialize_context_usage_payload
from loushang.protocol import require_json_value

_MESSAGE_CODEC = create_agent_transcript_message_codec()
serialize_agent_message = _MESSAGE_CODEC.serialize

_FIRST_CAP_RE = re.compile(r"(.)([A-Z][a-z]+)")
_ALL_CAP_RE = re.compile(r"([a-z0-9])([A-Z])")


def _snake_case_key(key: object) -> str:
    text = str(key)
    text = _FIRST_CAP_RE.sub(r"\1_\2", text)
    return _ALL_CAP_RE.sub(r"\1_\2", text).lower()


def snake_case_json_keys(value: object) -> object:
    """Normalize event payload keys without changing enum/string values."""

    if isinstance(value, Mapping):
        return {
            _snake_case_key(key): snake_case_json_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [snake_case_json_keys(item) for item in value]
    if isinstance(value, tuple):
        return [snake_case_json_keys(item) for item in value]
    return value


def serialize_session_event(event: Mapping[str, object]) -> dict[str, Any]:
    return snake_case_json_keys(_serialize_session_event(event))  # type: ignore[return-value]


def _serialize_session_event(event: Mapping[str, object]) -> dict[str, Any]:
    event_type = event["type"]

    if event_type in {"agent_start", "turn_start"}:
        return {"type": event_type}
    if event_type == "agent_end":
        return {
            "type": event_type,
            "messages": [
                serialize_agent_message(message) for message in event["messages"]
            ],
        }
    if event_type == "turn_end":
        return {
            "type": event_type,
            "message": serialize_agent_message(event["message"]),
            "tool_results": [
                serialize_agent_message(message) for message in event["tool_results"]
            ],
        }
    if event_type == "message_start":
        return {
            "type": event_type,
            "message": serialize_agent_message(event["message"]),
        }
    if event_type == "message_update":
        return {
            "type": event_type,
            "message": serialize_agent_message(event["message"]),
            "assistant_message_event": serialize_assistant_message_event(
                event["assistant_message_event"]
            ),
        }
    if event_type == "message_end":
        return {
            "type": event_type,
            "message": serialize_agent_message(event["message"]),
        }
    if event_type == "tool_execution_start":
        return {
            "type": event_type,
            "tool_call_id": event["tool_call_id"],
            "tool_name": event["tool_name"],
            "args": require_json_value(event["args"], name="tool_event.args"),
        }
    if event_type == "tool_execution_update":
        return {
            "type": event_type,
            "tool_call_id": event["tool_call_id"],
            "tool_name": event["tool_name"],
            "args": require_json_value(event["args"], name="tool_event.args"),
            "partial_result": serialize_tool_result(event["partial_result"]),
        }
    if event_type == "tool_execution_end":
        payload = {
            "type": event_type,
            "tool_call_id": event["tool_call_id"],
            "tool_name": event["tool_name"],
            "result": serialize_tool_result(event["result"]),
            "is_error": event["is_error"],
        }
        if "duration_ms" in event:
            payload["duration_ms"] = event["duration_ms"]
        return payload
    if event_type == "queue_update":
        return {
            "type": event_type,
            "steering": list(event["steering"]),
            "follow_up": list(event["follow_up"]),
        }
    if event_type == "session_info_changed":
        return {"type": event_type, "name": event["name"]}
    if event_type == "compaction_start":
        payload: dict[str, Any] = {"type": event_type, "reason": event["reason"]}
        if "usage" in event:
            payload["usage"] = serialize_context_usage_payload(event["usage"])
        return payload
    if event_type == "compaction_end":
        payload: dict[str, Any] = {
            "type": event_type,
            "reason": event["reason"],
            "result": require_json_value(
                event["result"],
                name="compaction_event.result",
            ),
            "aborted": event["aborted"],
            "will_retry": event["will_retry"],
        }
        if "usage_before" in event:
            payload["usage_before"] = serialize_context_usage_payload(
                event["usage_before"]
            )
        if "usage_after" in event:
            payload["usage_after"] = serialize_context_usage_payload(
                event["usage_after"]
            )
        if "error_message" in event:
            payload["error_message"] = event["error_message"]
        return payload
    if event_type == "auto_retry_start":
        return {
            "type": event_type,
            "attempt": event["attempt"],
            "max_attempts": event["max_attempts"],
            "delay_ms": event["delay_ms"],
            "error_message": event["error_message"],
        }
    if event_type == "auto_retry_end":
        payload = {
            "type": event_type,
            "success": event["success"],
            "attempt": event["attempt"],
        }
        if "final_error" in event:
            payload["final_error"] = event["final_error"]
        return payload
    if event_type == "package_progress":
        return {
            "type": event_type,
            "progress_type": event["progress_type"],
            "action": event["action"],
            "source": event["source"],
            "message": event["message"],
            "target_path": event["target_path"],
        }
    if event_type == "branch_summary_start":
        return {
            "type": event_type,
            "target_id": event["target_id"],
            "old_leaf_id": event["old_leaf_id"],
            "summarize": event["summarize"],
        }
    if event_type == "branch_summary_end":
        payload = {
            "type": event_type,
            "target_id": event["target_id"],
            "old_leaf_id": event["old_leaf_id"],
            "new_leaf_id": event["new_leaf_id"],
            "summary_entry_id": event["summary_entry_id"],
            "cancelled": event["cancelled"],
            "aborted": event["aborted"],
        }
        if "error_message" in event:
            payload["error_message"] = event["error_message"]
        return payload
    raise ValueError(f"Unsupported session event type: {event_type}")


__all__ = ["serialize_session_event", "snake_case_json_keys"]
