from __future__ import annotations

from typing import Any

from loushang.agent.json_codec import serialize_tool_result
from loushang.ai.json_codec import serialize_assistant_message_event
from loushang.coding.event.types import AgentSessionEvent
from loushang.harness.agent_transcript import create_agent_transcript_message_codec
from loushang.harness.context import serialize_context_usage_payload
from loushang.protocol import require_json_value

_MESSAGE_CODEC = create_agent_transcript_message_codec()
serialize_agent_message = _MESSAGE_CODEC.serialize


def serialize_session_event(event: AgentSessionEvent) -> dict[str, Any]:
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
            "toolResults": [
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
            "assistantMessageEvent": serialize_assistant_message_event(
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
            "toolCallId": event["tool_call_id"],
            "toolName": event["tool_name"],
            "args": require_json_value(event["args"], name="tool_event.args"),
        }
    if event_type == "tool_execution_update":
        return {
            "type": event_type,
            "toolCallId": event["tool_call_id"],
            "toolName": event["tool_name"],
            "args": require_json_value(event["args"], name="tool_event.args"),
            "partialResult": serialize_tool_result(event["partial_result"]),
        }
    if event_type == "tool_execution_end":
        payload = {
            "type": event_type,
            "toolCallId": event["tool_call_id"],
            "toolName": event["tool_name"],
            "result": serialize_tool_result(event["result"]),
            "isError": event["is_error"],
        }
        if "duration_ms" in event:
            payload["durationMs"] = event["duration_ms"]
        return payload
    if event_type == "queue_update":
        return {
            "type": event_type,
            "steering": list(event["steering"]),
            "followUp": list(event["follow_up"]),
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
            "willRetry": event["will_retry"],
        }
        if "usage_before" in event:
            payload["usageBefore"] = serialize_context_usage_payload(
                event["usage_before"]
            )
        if "usage_after" in event:
            payload["usageAfter"] = serialize_context_usage_payload(
                event["usage_after"]
            )
        if "error_message" in event:
            payload["errorMessage"] = event["error_message"]
        return payload
    if event_type == "auto_retry_start":
        return {
            "type": event_type,
            "attempt": event["attempt"],
            "maxAttempts": event["max_attempts"],
            "delayMs": event["delay_ms"],
            "errorMessage": event["error_message"],
        }
    if event_type == "auto_retry_end":
        payload = {
            "type": event_type,
            "success": event["success"],
            "attempt": event["attempt"],
        }
        if "final_error" in event:
            payload["finalError"] = event["final_error"]
        return payload
    if event_type == "package_progress":
        return {
            "type": event_type,
            "progressType": event["progress_type"],
            "action": event["action"],
            "source": event["source"],
            "message": event["message"],
            "targetPath": event["target_path"],
        }
    if event_type == "branch_summary_start":
        return {
            "type": event_type,
            "targetId": event["target_id"],
            "oldLeafId": event["old_leaf_id"],
            "summarize": event["summarize"],
        }
    if event_type == "branch_summary_end":
        payload = {
            "type": event_type,
            "targetId": event["target_id"],
            "oldLeafId": event["old_leaf_id"],
            "newLeafId": event["new_leaf_id"],
            "summaryEntryId": event["summary_entry_id"],
            "cancelled": event["cancelled"],
            "aborted": event["aborted"],
        }
        if "error_message" in event:
            payload["errorMessage"] = event["error_message"]
        return payload
    raise ValueError(f"Unsupported session event type: {event_type}")
