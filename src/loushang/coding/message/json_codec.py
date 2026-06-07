from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from loushang.agent import AgentMessage, AgentToolResult
from loushang.ai.types import (
    AssistantMessage,
    AssistantMessageEvent,
    ImagePart,
    Message,
    TextPart,
    ThinkingPart,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from loushang.coding.message.custom_messages import (
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
)
from loushang.coding.message.entries import SessionHeader


def _get_key(payload: dict[str, Any], camel_key: str, snake_key: str) -> Any:
    if camel_key in payload:
        return payload[camel_key]
    return payload[snake_key]


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


def serialize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): serialize_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [serialize_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return serialize_json_value(asdict(value))
    return repr(value)


def serialize_content_part(part: TextPart | ImagePart | ThinkingPart | ToolCall) -> dict[str, Any]:
    if isinstance(part, TextPart):
        return {
            "type": "text",
            "text": part.text,
            "textSignature": part.text_signature,
        }
    if isinstance(part, ImagePart):
        return {
            "type": "image",
            "data": part.data,
            "mimeType": part.mime_type,
        }
    if isinstance(part, ThinkingPart):
        return {
            "type": "thinking",
            "thinking": part.thinking,
            "thinkingSignature": part.thinking_signature,
            "redacted": part.redacted,
        }
    if isinstance(part, ToolCall):
        return {
            "type": "toolCall",
            "id": part.id,
            "name": part.name,
            "arguments": part.arguments,
            "thoughtSignature": part.thought_signature,
        }
    raise ValueError(f"Unsupported content part type: {type(part)!r}")


def deserialize_content_part(payload: dict[str, Any]) -> TextPart | ImagePart | ThinkingPart | ToolCall:
    part_type = payload["type"]
    if part_type == "text":
        return TextPart(type="text", text=payload["text"], text_signature=payload.get("textSignature", payload.get("text_signature")))
    if part_type == "image":
        return ImagePart(type="image", data=payload["data"], mime_type=payload.get("mimeType", payload.get("mime_type")))
    if part_type == "thinking":
        return ThinkingPart(
            type="thinking",
            thinking=payload["thinking"],
            thinking_signature=payload.get("thinkingSignature", payload.get("thinking_signature")),
            redacted=payload.get("redacted", False),
        )
    if part_type == "toolCall":
        return ToolCall(
            type="toolCall",
            id=payload["id"],
            name=payload["name"],
            arguments=payload["arguments"],
            thought_signature=payload.get("thoughtSignature", payload.get("thought_signature")),
        )
    raise ValueError(f"Unsupported content part type: {part_type}")


def serialize_usage(usage: Usage) -> dict[str, Any]:
    cost = usage.cost
    return {
        "input": usage.input,
        "output": usage.output,
        "cacheRead": usage.cache_read,
        "cacheWrite": usage.cache_write,
        "totalTokens": usage.total_tokens,
        "cost": {
            "input": cost.get("input", 0.0),
            "output": cost.get("output", 0.0),
            "cacheRead": cost.get("cacheRead", cost.get("cache_read", 0.0)),
            "cacheWrite": cost.get("cacheWrite", cost.get("cache_write", 0.0)),
            "total": cost.get("total", 0.0),
        },
    }


def deserialize_usage(payload: dict[str, Any]) -> Usage:
    cost = payload.get("cost", {})
    return Usage(
        input=payload["input"],
        output=payload["output"],
        cache_read=_get_key(payload, "cacheRead", "cache_read"),
        cache_write=_get_key(payload, "cacheWrite", "cache_write"),
        total_tokens=_get_key(payload, "totalTokens", "total_tokens"),
        cost={
            "input": cost.get("input", 0.0),
            "output": cost.get("output", 0.0),
            "cacheRead": cost.get("cacheRead", cost.get("cache_read", 0.0)),
            "cacheWrite": cost.get("cacheWrite", cost.get("cache_write", 0.0)),
            "total": cost.get("total", 0.0),
        },
    )


def serialize_tool_result(result: AgentToolResult[Any]) -> dict[str, Any]:
    return {
        "content": [serialize_content_part(part) for part in result.content],
        "details": serialize_json_value(result.details),
        "terminate": result.terminate,
    }


def serialize_ai_message(message: Message) -> dict[str, Any]:
    if isinstance(message, UserMessage):
        content = message.content
        return {
            "role": "user",
            "content": [serialize_content_part(part) for part in content] if isinstance(content, list) else content,
            "timestamp": message.timestamp,
        }
    if isinstance(message, AssistantMessage):
        payload = {
            "role": "assistant",
            "content": [serialize_content_part(part) for part in message.content],
            "api": message.api,
            "provider": message.provider,
            "model": message.model,
            "responseId": message.response_id,
            "usage": serialize_usage(message.usage),
            "stopReason": message.stop_reason,
            "errorMessage": message.error_message,
            "timestamp": message.timestamp,
        }
        if message.response_model is not None:
            payload["responseModel"] = message.response_model
        return payload
    if isinstance(message, ToolResultMessage):
        return {
            "role": "toolResult",
            "toolCallId": message.tool_call_id,
            "toolName": message.tool_name,
            "content": [serialize_content_part(part) for part in message.content],
            "isError": message.is_error,
            "timestamp": message.timestamp,
            "details": serialize_json_value(message.details),
        }
    raise ValueError(f"Unsupported AI message type: {type(message)!r}")


def deserialize_ai_message(payload: dict[str, Any]) -> Message:
    role = payload["role"]
    if role == "user":
        content = payload["content"]
        return UserMessage(
            role="user",
            content=[deserialize_content_part(part) for part in content] if isinstance(content, list) else content,
            timestamp=payload["timestamp"],
        )
    if role == "assistant":
        return AssistantMessage(
            role="assistant",
            content=[deserialize_content_part(part) for part in payload["content"]],
            api=payload["api"],
            provider=payload["provider"],
            model=payload["model"],
            response_id=payload.get("responseId", payload.get("response_id")),
            usage=deserialize_usage(payload["usage"]),
            stop_reason=payload.get("stopReason", payload.get("stop_reason")),
            error_message=payload.get("errorMessage", payload.get("error_message")),
            timestamp=payload["timestamp"],
            response_model=payload.get("responseModel", payload.get("response_model")),
        )
    if role == "toolResult":
        return ToolResultMessage(
            role="toolResult",
            tool_call_id=payload.get("toolCallId", payload.get("tool_call_id")),
            tool_name=payload.get("toolName", payload.get("tool_name")),
            content=[deserialize_content_part(part) for part in payload["content"]],
            is_error=payload.get("isError", payload.get("is_error")),
            timestamp=payload["timestamp"],
            details=payload.get("details"),
        )
    raise ValueError(f"Unsupported AI message role: {role}")


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


def serialize_agent_message(message: AgentMessage) -> dict[str, Any]:
    if isinstance(message, UserMessage | AssistantMessage | ToolResultMessage):
        return serialize_ai_message(message)
    return serialize_custom_message(message)


def deserialize_agent_message(payload: dict[str, Any]) -> AgentMessage:
    role = payload["role"]
    if role in {"user", "assistant", "toolResult"}:
        return deserialize_ai_message(payload)
    return deserialize_custom_message(payload)


def serialize_assistant_message_event(event: AssistantMessageEvent) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": event["type"]}
    event_type = event["type"]

    if "partial" in event:
        payload["partial"] = serialize_ai_message(event["partial"])
    if event_type == "start":
        return payload
    if event_type in {"text_start", "thinking_start", "toolcall_start", "image_start"}:
        payload["contentIndex"] = event["content_index"]
        return payload
    if event_type in {"text_delta", "thinking_delta", "toolcall_delta"}:
        payload["contentIndex"] = event["content_index"]
        payload["delta"] = event["delta"]
        return payload
    if event_type in {"text_end", "thinking_end"}:
        payload["contentIndex"] = event["content_index"]
        payload["content"] = event["content"]
        return payload
    if event_type == "toolcall_end":
        payload["contentIndex"] = event["content_index"]
        payload["toolCall"] = serialize_content_part(event["tool_call"])
        return payload
    if event_type == "image_end":
        payload["contentIndex"] = event["content_index"]
        payload["image"] = serialize_content_part(event["image"])
        return payload
    if event_type == "done":
        payload["reason"] = event["reason"]
        payload["message"] = serialize_ai_message(event["message"])
        return payload
    if event_type == "error":
        payload["reason"] = event["reason"]
        payload["error"] = serialize_ai_message(event["error"])
        return payload
    raise ValueError(f"Unsupported assistant message event type: {event_type}")
