from __future__ import annotations

from typing import Any

from loushang.agent import AgentMessage
from loushang.agent.json_codec import (
    AgentMessageJsonCodec,
    CustomMessageJsonCodec,
    serialize_tool_result,
)
from loushang.ai.json_codec import (
    deserialize_content_part,
    deserialize_usage,
    serialize_assistant_message_event,
    serialize_content_part,
    serialize_json_value,
    serialize_usage,
)
from loushang.ai.json_codec import (
    deserialize_message as deserialize_ai_message,
)
from loushang.ai.json_codec import (
    serialize_message as serialize_ai_message,
)
from loushang.coding.message.custom_messages import (
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
)
from loushang.coding.message.entries import SessionHeader


def serialize_session_header(header: SessionHeader) -> dict[str, Any]:
    return {
        "type": header.type,
        "version": header.version,
        "id": header.id,
        "timestamp": header.timestamp,
        "cwd": header.cwd,
        "parentSession": header.parent_session,
    }


def deserialize_session_header(payload: dict[str, Any]) -> SessionHeader:
    return SessionHeader(
        type=payload["type"],
        version=payload["version"],
        id=payload["id"],
        timestamp=payload["timestamp"],
        cwd=payload["cwd"],
        parent_session=payload.get("parentSession"),
    )


def serialize_custom_message(message: AgentMessage) -> dict[str, Any]:
    if isinstance(message, BashExecutionMessage):
        return {
            "role": "bashExecution",
            "command": message.command,
            "output": message.output,
            "exitCode": message.exit_code,
            "cancelled": message.cancelled,
            "truncated": message.truncated,
            "fullOutputPath": message.full_output_path,
            "timestamp": message.timestamp,
            "excludeFromContext": message.exclude_from_context,
        }
    if isinstance(message, CustomMessage):
        content = message.content
        return {
            "role": "custom",
            "customType": message.custom_type,
            "content": [serialize_content_part(part) for part in content] if isinstance(content, list) else content,
            "display": message.display,
            "details": serialize_json_value(message.details),
            "timestamp": message.timestamp,
        }
    if isinstance(message, BranchSummaryMessage):
        return {
            "role": "branchSummary",
            "summary": message.summary,
            "fromId": message.from_id,
            "timestamp": message.timestamp,
        }
    if isinstance(message, CompactionSummaryMessage):
        return {
            "role": "compactionSummary",
            "summary": message.summary,
            "tokensBefore": message.tokens_before,
            "timestamp": message.timestamp,
        }
    raise ValueError(f"Unsupported custom agent message type: {type(message)!r}")


def deserialize_custom_message(payload: dict[str, Any]) -> AgentMessage:
    role = payload["role"]
    if role == "bashExecution":
        return BashExecutionMessage(
            role="bashExecution",
            command=payload["command"],
            output=payload["output"],
            exit_code=payload.get("exitCode"),
            cancelled=payload["cancelled"],
            truncated=payload["truncated"],
            full_output_path=payload.get("fullOutputPath", payload.get("full_output_path")),
            timestamp=payload["timestamp"],
            exclude_from_context=payload.get("excludeFromContext", payload.get("exclude_from_context", False)),
        )
    if role == "custom":
        content = payload["content"]
        return CustomMessage(
            role="custom",
            custom_type=payload.get("customType", payload.get("custom_type")),
            content=[deserialize_content_part(part) for part in content] if isinstance(content, list) else content,
            display=payload["display"],
            details=payload.get("details"),
            timestamp=payload["timestamp"],
        )
    if role == "branchSummary":
        return BranchSummaryMessage(
            role="branchSummary",
            summary=payload["summary"],
            from_id=payload.get("fromId", payload.get("from_id")),
            timestamp=payload["timestamp"],
        )
    if role == "compactionSummary":
        return CompactionSummaryMessage(
            role="compactionSummary",
            summary=payload["summary"],
            tokens_before=payload.get("tokensBefore", payload.get("tokens_before")),
            timestamp=payload["timestamp"],
        )
    raise ValueError(f"Unsupported custom message role: {role}")


_CODING_MESSAGE_CODEC = AgentMessageJsonCodec(
    CustomMessageJsonCodec(
        role=role,
        message_type=message_type,
        serialize=serialize_custom_message,
        deserialize=deserialize_custom_message,
    )
    for role, message_type in (
        ("bashExecution", BashExecutionMessage),
        ("custom", CustomMessage),
        ("branchSummary", BranchSummaryMessage),
        ("compactionSummary", CompactionSummaryMessage),
    )
)


def serialize_agent_message(message: AgentMessage) -> dict[str, Any]:
    return _CODING_MESSAGE_CODEC.serialize(message)


def deserialize_agent_message(payload: dict[str, Any]) -> AgentMessage:
    return _CODING_MESSAGE_CODEC.deserialize(payload)


__all__ = [
    "deserialize_agent_message",
    "deserialize_ai_message",
    "deserialize_content_part",
    "deserialize_custom_message",
    "deserialize_session_header",
    "deserialize_usage",
    "serialize_agent_message",
    "serialize_ai_message",
    "serialize_assistant_message_event",
    "serialize_content_part",
    "serialize_custom_message",
    "serialize_json_value",
    "serialize_session_header",
    "serialize_tool_result",
    "serialize_usage",
]
