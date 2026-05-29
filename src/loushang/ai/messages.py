from __future__ import annotations

from typing import Any, cast

from loushang.ai.model.registry import resolve_model_api
from loushang.ai.tool import (
    normalize_tool_call_id_for_model,
    transform_messages,
)
from loushang.ai.tool.transform import (
    PairingMode,
    coerce_cross_provider_assistant_message,
)
from loushang.ai.types import (
    AssistantMessage,
    ImagePart,
    TextPart,
    ThinkingPart,
    Tool,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)


def normalize_messages(
    messages: list[object],
    *,
    tools: list[Tool] | None = None,
    model=None,
    pairing_mode: PairingMode = "repair",
) -> list[object]:
    messages = [canonicalize_message(message) for message in messages]
    normalize_tool_call_id = None
    if model is not None:

        def _normalize_tool_call_id(
            tool_call_id: str, _message: AssistantMessage
        ) -> str:
            return normalize_tool_call_id_for_model(tool_call_id, model)

        normalize_tool_call_id = _normalize_tool_call_id

    transformed = transform_messages(
        messages,
        normalize_tool_call_id=normalize_tool_call_id,
        pairing_mode=pairing_mode,
    )
    transformed = [canonicalize_user_message(message) for message in transformed]

    if model is not None:
        target_api = resolve_model_api(model)
        if isinstance(target_api, str) and target_api:
            transformed = [
                coerce_cross_provider_assistant_message(
                    message,
                    target_api=target_api,
                    target_provider=getattr(model, "provider_id", None),
                    target_model=getattr(model, "id", None),
                )
                if isinstance(message, AssistantMessage)
                else message
                for message in transformed
            ]

    # Tool arguments are validated before execution. Provider-context projection
    # must keep historical malformed calls recoverable when they already have
    # matching error tool results in the transcript.
    return transformed


def canonicalize_message(message: object) -> object:
    if not isinstance(message, dict):
        return message
    role = message.get("role")
    if role == "assistant":
        return _assistant_message_from_dict(message)
    if role == "toolResult":
        return _tool_result_message_from_dict(message)
    return message


def canonicalize_user_message(message: object) -> object:
    if isinstance(message, UserMessage):
        return UserMessage(
            role=message.role,
            content=cast(
                list[TextPart | ImagePart],
                canonicalize_user_content(message.content),
            ),
            timestamp=message.timestamp,
        )

    if isinstance(message, dict) and message.get("role") == "user":
        normalized = dict(message)
        normalized["content"] = canonicalize_user_content(
            message.get("content"), prefer_dict_parts=True
        )
        return normalized

    return message


def _assistant_message_from_dict(message: dict[str, Any]) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[
            _assistant_content_part(part)
            for part in _content_parts(message.get("content"))
        ],
        api=str(message.get("api", "")),
        provider=str(message.get("provider", "")),
        model=str(message.get("model", "")),
        response_id=_optional_str(message.get("response_id", message.get("responseId"))),
        usage=_usage_from_dict(message.get("usage")),
        stop_reason=message.get("stop_reason", message.get("stopReason", "stop")),  # type: ignore[arg-type]
        error_message=_optional_str(message.get("error_message", message.get("errorMessage"))),
        timestamp=_float_or_default(message.get("timestamp")),
        response_model=_optional_str(
            message.get("response_model", message.get("responseModel"))
        ),
    )


def _tool_result_message_from_dict(message: dict[str, Any]) -> ToolResultMessage:
    content = canonicalize_user_content(message.get("content") or [])
    return ToolResultMessage(
        role="toolResult",
        tool_call_id=str(message.get("tool_call_id", message.get("toolCallId", ""))),
        tool_name=str(message.get("tool_name", message.get("toolName", ""))),
        content=content,  # type: ignore[arg-type]
        is_error=bool(message.get("is_error", message.get("isError", False))),
        timestamp=_float_or_default(message.get("timestamp")),
        details=message.get("details"),
    )


def _assistant_content_part_from_dict(
    part: dict[str, Any],
) -> TextPart | ThinkingPart | ToolCall | ImagePart:
    part_type = part.get("type")
    if part_type in {"text", "image"}:
        return _part_from_dict(part)
    if part_type == "thinking":
        return ThinkingPart(
            type="thinking",
            thinking=str(part.get("thinking", "")),
            thinking_signature=_optional_str(
                part.get("thinking_signature", part.get("thinkingSignature"))
            ),
            redacted=bool(part.get("redacted", False)),
        )
    if part_type == "toolCall":
        arguments = part.get("arguments")
        return ToolCall(
            type="toolCall",
            id=str(part.get("id", "")),
            name=str(part.get("name", "")),
            arguments=arguments if isinstance(arguments, dict) else {},
            thought_signature=_optional_str(
                part.get("thought_signature", part.get("thoughtSignature"))
            ),
        )
    raise TypeError(f"Unsupported assistant content part type: {part_type!r}")


def _content_parts(content: object) -> list[Any]:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, dict):
        return [content]
    if not isinstance(content, list):
        raise TypeError(f"Unsupported message content type: {type(content)!r}")
    return list(content)


def _assistant_content_part(
    part: dict[str, Any] | TextPart | ThinkingPart | ToolCall | ImagePart
) -> TextPart | ThinkingPart | ToolCall | ImagePart:
    if isinstance(part, dict):
        return _assistant_content_part_from_dict(part)
    if isinstance(part, (TextPart, ThinkingPart, ToolCall, ImagePart)):
        return part
    raise TypeError(f"Unsupported assistant content part type: {type(part)!r}")


def _usage_from_dict(value: object) -> Usage:
    if isinstance(value, Usage):
        return value
    if not isinstance(value, dict):
        value = {}
    return Usage(
        input=_int_or_default(value.get("input")),
        output=_int_or_default(value.get("output")),
        cache_read=_int_or_default(value.get("cache_read", value.get("cacheRead"))),
        cache_write=_int_or_default(
            value.get("cache_write", value.get("cacheWrite"))
        ),
        total_tokens=_int_or_default(
            value.get("total_tokens", value.get("totalTokens"))
        ),
        cost=dict(value.get("cost") or {}),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_default(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str | bytes | bytearray | int | float):
        try:
            return int(value)
        except ValueError:
            return default
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return default


def _float_or_default(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def canonicalize_user_content(
    content: object,
    *,
    prefer_dict_parts: bool = False,
) -> list[TextPart | ImagePart] | list[dict[str, Any]]:
    if isinstance(content, str):
        if prefer_dict_parts:
            return [{"type": "text", "text": content}]
        return cast(
            list[TextPart | ImagePart],
            [TextPart(type="text", text=content)],
        )

    if isinstance(content, dict):
        return [dict(content)] if prefer_dict_parts else [_part_from_dict(content)]

    if not isinstance(content, list):
        raise TypeError(f"Unsupported user content type: {type(content)!r}")

    if prefer_dict_parts:
        normalized_dict_parts: list[dict[str, Any]] = []
        for part in content:
            if isinstance(part, dict):
                normalized_dict_parts.append(dict(part))
                continue
            normalized_dict_parts.append(_part_to_dict(part))
        return normalized_dict_parts

    normalized_parts: list[TextPart | ImagePart] = []
    for part in content:
        if isinstance(part, dict):
            normalized_parts.append(_part_from_dict(part))
            continue
        normalized_parts.append(cast(TextPart | ImagePart, part))
    return normalized_parts


def _part_from_dict(part: dict[str, Any]) -> TextPart | ImagePart:
    part_type = part.get("type")
    if part_type == "text":
        return TextPart(
            type="text",
            text=str(part.get("text", "")),
            text_signature=part.get("text_signature") or part.get("textSignature"),
        )
    if part_type == "image":
        mime_type = part.get("mime_type") or part.get("mimeType")
        return ImagePart(
            type="image",
            data=str(part.get("data", "")),
            mime_type=str(mime_type or ""),
        )
    raise TypeError(f"Unsupported user content part type: {part_type!r}")


def _part_to_dict(part: object) -> dict[str, Any]:
    part_type = getattr(part, "type", None)
    if part_type == "text":
        payload: dict[str, Any] = {
            "type": "text",
            "text": getattr(part, "text", ""),
        }
        text_signature = getattr(part, "text_signature", None)
        if text_signature is not None:
            payload["text_signature"] = text_signature
        return payload
    if part_type == "image":
        return {
            "type": "image",
            "data": getattr(part, "data", ""),
            "mime_type": getattr(part, "mime_type", ""),
        }
    raise TypeError(f"Unsupported user content part object: {type(part)!r}")
