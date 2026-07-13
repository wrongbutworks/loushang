from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any, cast

from loushang.ai.diagnostics import (
    NormalizationDiagnostic,
    sort_normalization_diagnostics,
)
from loushang.ai.model.registry import resolve_model_api
from loushang.ai.tool import (
    normalize_tool_call_id_for_model,
)
from loushang.ai.tool.transform import (
    PairingMode,
    coerce_cross_provider_assistant_message_result,
    transform_messages_result,
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
    UsageCost,
    UserMessage,
)


@dataclass(frozen=True)
class MessageNormalizationResult:
    messages: list[object]
    diagnostics: tuple[NormalizationDiagnostic, ...] = ()


def normalize_messages(
    messages: list[object],
    *,
    tools: list[Tool] | None = None,
    model=None,
    pairing_mode: PairingMode = "strict",
) -> list[object]:
    return normalize_messages_result(
        messages,
        tools=tools,
        model=model,
        pairing_mode=pairing_mode,
    ).messages


def normalize_messages_result(
    messages: list[object],
    *,
    tools: list[Tool] | None = None,
    model=None,
    pairing_mode: PairingMode = "strict",
    message_paths: list[str] | None = None,
) -> MessageNormalizationResult:
    messages = [canonicalize_message(message) for message in messages]
    diagnostics: list[NormalizationDiagnostic] = []
    normalize_tool_call_id = None
    if model is not None:

        def _normalize_tool_call_id(
            tool_call_id: str, _message: AssistantMessage
        ) -> str:
            return normalize_tool_call_id_for_model(tool_call_id, model)

        normalize_tool_call_id = _normalize_tool_call_id

    transform_result = transform_messages_result(
        messages,
        normalize_tool_call_id=normalize_tool_call_id,
        pairing_mode=pairing_mode,
        message_paths=message_paths,
    )
    transformed = transform_result.messages
    transformed_paths = list(transform_result.message_paths)
    diagnostics.extend(transform_result.diagnostics)
    transformed = [canonicalize_user_message(message) for message in transformed]

    if model is not None:
        target_api = resolve_model_api(model)
        if isinstance(target_api, str) and target_api:
            coerced: list[object] = []
            for index, message in enumerate(transformed):
                if not isinstance(message, AssistantMessage):
                    coerced.append(message)
                    continue
                coercion_result = coerce_cross_provider_assistant_message_result(
                    message,
                    target_api=target_api,
                    target_provider=getattr(model, "provider_id", None),
                    target_model=getattr(model, "id", None),
                    path=transformed_paths[index],
                )
                coerced.append(coercion_result.message)
                diagnostics.extend(coercion_result.diagnostics)
            transformed = coerced

    # Tool arguments are validated before execution. Provider-context projection
    # must keep historical malformed calls recoverable when they already have
    # matching error tool results in the transcript.
    return MessageNormalizationResult(
        messages=transformed,
        diagnostics=sort_normalization_diagnostics(diagnostics),
    )


def canonicalize_message(message: object) -> object:
    if not isinstance(message, Mapping):
        return message
    message = dict(message)
    role = message.get("role")
    if role == "user":
        return _user_message_from_dict(message)
    if role == "assistant":
        return _assistant_message_from_dict(message)
    if role == "toolResult":
        return _tool_result_message_from_dict(message)
    raise TypeError(f"Unsupported message role: {role!r}")


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

    if isinstance(message, Mapping):
        return canonicalize_message(message)

    return message


def _user_message_from_dict(message: dict[str, Any]) -> UserMessage:
    return UserMessage(
        role="user",
        content=cast(
            list[TextPart | ImagePart],
            canonicalize_user_content(message.get("content")),
        ),
        timestamp=_float_or_default(message.get("timestamp")),
    )


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
        response_id=_optional_str(
            message.get("response_id", message.get("responseId"))
        ),
        usage=_usage_from_dict(message.get("usage")),
        stop_reason=message.get("stop_reason", message.get("stopReason", "stop")),  # type: ignore[arg-type]
        error_message=_optional_str(
            message.get("error_message", message.get("errorMessage"))
        ),
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
        terminate=message.get("terminate", False) is True,
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
    if isinstance(content, Mapping):
        return [dict(content)]
    if not isinstance(content, list):
        raise TypeError(f"Unsupported message content type: {type(content)!r}")
    return list(content)


def _assistant_content_part(
    part: dict[str, Any] | TextPart | ThinkingPart | ToolCall | ImagePart,
) -> TextPart | ThinkingPart | ToolCall | ImagePart:
    if isinstance(part, Mapping):
        return _assistant_content_part_from_dict(dict(part))
    if isinstance(part, (TextPart, ThinkingPart, ToolCall, ImagePart)):
        return part
    raise TypeError(f"Unsupported assistant content part type: {type(part)!r}")


def _usage_from_dict(value: object) -> Usage:
    if isinstance(value, Usage):
        return value
    if not isinstance(value, Mapping):
        value = {}
    else:
        value = dict(value)
    cost_raw = value.get("cost")
    cost = _canonical_cost(cost_raw if isinstance(cost_raw, dict) else None)
    return Usage(
        input=_int_or_default(value.get("input")),
        output=_int_or_default(value.get("output")),
        cache_read=_int_or_default(value.get("cache_read", value.get("cacheRead"))),
        cache_write=_int_or_default(value.get("cache_write", value.get("cacheWrite"))),
        total_tokens=_int_or_default(
            value.get("total_tokens", value.get("totalTokens"))
        ),
        cost=cost,
    )


def _canonical_cost(cost: Mapping[str, object] | None) -> UsageCost | None:
    if cost is None:
        return None
    input_cost = _cost_number(cost, "input")
    output_cost = _cost_number(cost, "output")
    cache_read = _cost_number(cost, "cacheRead", "cache_read")
    cache_write = _cost_number(cost, "cacheWrite", "cache_write")
    total = _cost_number(cost, "total")
    if (
        input_cost is None
        or output_cost is None
        or cache_read is None
        or cache_write is None
        or total is None
    ):
        return None
    return {
        "input": input_cost,
        "output": output_cost,
        "cacheRead": cache_read,
        "cacheWrite": cache_write,
        "total": total,
    }


def _cost_number(
    cost: Mapping[str, object], key: str, alias: str | None = None
) -> float | None:
    if key in cost:
        value = cost[key]
    elif alias is not None and alias in cost:
        value = cost[alias]
    else:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value < 0
    ):
        return None
    return float(value)


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
) -> list[TextPart | ImagePart]:
    if isinstance(content, str):
        return cast(
            list[TextPart | ImagePart],
            [TextPart(type="text", text=content)],
        )

    if isinstance(content, Mapping):
        return [_part_from_dict(dict(content))]

    if not isinstance(content, list):
        raise TypeError(f"Unsupported user content type: {type(content)!r}")

    normalized_parts: list[TextPart | ImagePart] = []
    for part in content:
        if isinstance(part, Mapping):
            normalized_parts.append(_part_from_dict(dict(part)))
            continue
        if isinstance(part, (TextPart, ImagePart)):
            normalized_parts.append(part)
            continue
        raise TypeError(f"Unsupported user content part object: {type(part)!r}")
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
