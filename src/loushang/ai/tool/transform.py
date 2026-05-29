from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from typing import cast

from loushang.ai.model.registry import resolve_model_api
from loushang.ai.options import PairingMode
from loushang.ai.types import (
    AssistantMessage,
    TextPart,
    ThinkingPart,
    ToolCall,
    ToolResultMessage,
)

_ANTHROPIC_TOOL_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MISSING_TOOL_RESULT_TEXT = "No result provided"
TOOL_RESULTS_PROCESSED_ASSISTANT_TEXT = "I have processed the tool results."
SYNTHETIC_TOOL_RESULT_REASON = "missing_tool_result"


def transform_messages(
    messages: list[object],
    *,
    normalize_tool_call_id: Callable[[str, AssistantMessage], str] | None = None,
    pairing_mode: PairingMode = "repair",
) -> list[object]:
    transformed: list[object] = []
    pending_tool_calls: list[ToolCall] = []
    pending_tool_call_map: dict[str, ToolCall] = {}
    existing_tool_result_ids: set[str] = set()
    closed_tool_call_ids: set[str] = set()
    tool_call_id_map: dict[str, str] = {}

    for message in messages:
        if isinstance(message, AssistantMessage):
            if pending_tool_calls:
                if pairing_mode == "strict":
                    raise ValueError("Missing tool results before next message")
                transformed.extend(
                    _synthetic_tool_results(
                        pending_tool_calls, existing_tool_result_ids
                    )
                )
                closed_tool_call_ids.update(
                    tool_call.id for tool_call in pending_tool_calls
                )
                pending_tool_calls = []
                pending_tool_call_map = {}
                existing_tool_result_ids = set()

            normalized_message = message
            normalized_content: list[object] = []
            current_tool_calls: list[ToolCall] = []
            changed = False

            for block in message.content:
                if isinstance(block, ToolCall):
                    next_id = (
                        normalize_tool_call_id(block.id, message)
                        if normalize_tool_call_id is not None
                        else block.id
                    )
                    if next_id != block.id:
                        tool_call_id_map[block.id] = next_id
                        block = ToolCall(
                            type=block.type,
                            id=next_id,
                            name=block.name,
                            arguments=block.arguments,
                        )
                        changed = True
                    current_tool_calls.append(block)
                    closed_tool_call_ids.discard(block.id)
                normalized_content.append(block)

            if normalized_message.stop_reason == "aborted":
                transformed.append(_aborted_boundary_message(normalized_message))
                continue
            if normalized_message.stop_reason == "error":
                continue

            if changed:
                normalized_message = AssistantMessage(
                    role=message.role,
                    content=normalized_content,  # type: ignore[arg-type]
                    api=message.api,
                    provider=message.provider,
                    model=message.model,
                    response_id=message.response_id,
                    usage=message.usage,
                    stop_reason=message.stop_reason,
                    error_message=message.error_message,
                    timestamp=message.timestamp,
                    response_model=message.response_model,
                )

            transformed.append(normalized_message)
            pending_tool_calls = current_tool_calls
            pending_tool_call_map = {
                tool_call.id: tool_call for tool_call in current_tool_calls
            }
            existing_tool_result_ids = set()
            continue

        if isinstance(message, ToolResultMessage):
            next_id = tool_call_id_map.get(message.tool_call_id, message.tool_call_id)
            if next_id != message.tool_call_id:
                message = ToolResultMessage(
                    role=message.role,
                    tool_call_id=next_id,
                    tool_name=message.tool_name,
                    content=message.content,
                    is_error=message.is_error,
                    timestamp=message.timestamp,
                    details=message.details,
                )
            if message.tool_call_id in closed_tool_call_ids:
                raise ValueError(
                    f"Late tool result for closed tool call: {message.tool_call_id!r}"
                )
            matched_tool_call = pending_tool_call_map.get(message.tool_call_id)
            if (
                pairing_mode == "strict"
                and not pending_tool_calls
                and matched_tool_call is None
            ):
                raise ValueError(
                    f"Orphaned tool result without pending tool call: {message.tool_call_id!r}"
                )
            if pending_tool_calls and matched_tool_call is None:
                raise ValueError(
                    f"Unknown tool result for pending tool calls: {message.tool_call_id!r}"
                )
            if (
                matched_tool_call is not None
                and matched_tool_call.name != message.tool_name
            ):
                raise ValueError(
                    f"Tool result name mismatch for {message.tool_call_id!r}: "
                    f"expected {matched_tool_call.name!r}, got {message.tool_name!r}"
                )
            if (
                matched_tool_call is not None
                and message.tool_call_id in existing_tool_result_ids
            ):
                raise ValueError(f"Duplicate tool result for {message.tool_call_id!r}")
            existing_tool_result_ids.add(message.tool_call_id)
            transformed.append(message)
            continue

        if pending_tool_calls:
            if pairing_mode == "strict":
                raise ValueError("Missing tool results before next message")
            transformed.extend(
                _synthetic_tool_results(pending_tool_calls, existing_tool_result_ids)
            )
            closed_tool_call_ids.update(
                tool_call.id for tool_call in pending_tool_calls
            )
            pending_tool_calls = []
            pending_tool_call_map = {}
            existing_tool_result_ids = set()

        transformed.append(message)

    if pending_tool_calls:
        if pairing_mode == "strict":
            raise ValueError("Missing tool results before next message")
        transformed.extend(
            _synthetic_tool_results(pending_tool_calls, existing_tool_result_ids)
        )
        closed_tool_call_ids.update(tool_call.id for tool_call in pending_tool_calls)

    return transformed


def _aborted_boundary_message(message: AssistantMessage) -> AssistantMessage:
    text = _assistant_text(message) or message.error_message or "Request aborted by user"
    return AssistantMessage(
        role=message.role,
        content=[TextPart(type="text", text=text)],
        api=message.api,
        provider=message.provider,
        model=message.model,
        response_id=message.response_id,
        usage=message.usage,
        stop_reason="stop",
        error_message=None,
        timestamp=message.timestamp,
        response_model=message.response_model,
    )


def _assistant_text(message: AssistantMessage) -> str:
    parts = [
        block.text.strip()
        for block in message.content
        if isinstance(block, TextPart) and block.text.strip()
    ]
    return "\n".join(parts)


def coerce_cross_provider_assistant_message(
    message: AssistantMessage,
    *,
    target_api: str,
    target_provider: str | None = None,
    target_model: str | None = None,
) -> AssistantMessage:
    same_model = (
        message.api == target_api
        and (target_provider is None or message.provider == target_provider)
        and (target_model is None or message.model == target_model)
    )
    if same_model or not message.api:
        return message
    coerced_content: list[object] = []
    changed = False
    for block in message.content:
        if isinstance(block, ThinkingPart):
            changed = True
            if block.redacted:
                continue
            if not block.thinking.strip():
                continue
            coerced_content.append(TextPart(type="text", text=block.thinking))
            continue
        if isinstance(block, TextPart):
            changed = changed or block.text_signature is not None
            coerced_content.append(TextPart(type="text", text=block.text))
            continue
        if isinstance(block, ToolCall):
            changed = changed or block.thought_signature is not None
            coerced_content.append(
                ToolCall(
                    type=block.type,
                    id=block.id,
                    name=block.name,
                    arguments=block.arguments,
                )
            )
            continue
        coerced_content.append(block)
    if not changed:
        return message
    return AssistantMessage(
        role=message.role,
        content=coerced_content,  # type: ignore[arg-type]
        api=message.api,
        provider=message.provider,
        model=message.model,
        response_id=message.response_id,
        usage=message.usage,
        stop_reason=message.stop_reason,
        error_message=message.error_message,
        timestamp=message.timestamp,
        response_model=message.response_model,
    )


def insert_assistant_bridge_after_tool_results(
    payload_messages: list[dict],
    *,
    assistant_content: str = TOOL_RESULTS_PROCESSED_ASSISTANT_TEXT,
) -> list[dict]:
    transformed: list[dict] = []
    previous_was_tool_result = False

    for message in payload_messages:
        if previous_was_tool_result and message.get("role") == "user":
            transformed.append({"role": "assistant", "content": assistant_content})
        transformed.append(message)
        previous_was_tool_result = (
            message.get("role") == "tool"
            or message.get("type") == "function_call_output"
        )

    return transformed


def group_consecutive_tool_results_as_user_messages(
    messages: list[object],
    *,
    build_tool_result_block: Callable[[ToolResultMessage], dict],
) -> list[object]:
    grouped: list[object] = []
    index = 0

    while index < len(messages):
        message = messages[index]
        if isinstance(message, ToolResultMessage):
            content_blocks: list[dict] = []
            while index < len(messages) and isinstance(
                messages[index], ToolResultMessage
            ):
                tool_result = cast(ToolResultMessage, messages[index])
                content_blocks.append(build_tool_result_block(tool_result))
                index += 1
            grouped.append({"role": "user", "content": content_blocks})
            continue

        grouped.append(message)
        index += 1

    return grouped


def merge_adjacent_user_payload_messages(
    messages: list[dict],
    *,
    normalize_user_content: Callable[[object], list[dict]],
) -> list[dict]:
    merged: list[dict] = []

    for message in messages:
        if (
            merged
            and merged[-1].get("role") == "user"
            and message.get("role") == "user"
        ):
            merged[-1]["content"] = normalize_user_content(
                merged[-1]["content"]
            ) + normalize_user_content(message["content"])
            continue
        merged.append(message)

    return merged


def normalize_tool_call_id_for_model(tool_call_id: str, model) -> str:
    if resolve_model_api(model) != "anthropic-messages":
        return tool_call_id
    if _ANTHROPIC_TOOL_CALL_ID_PATTERN.fullmatch(tool_call_id):
        return tool_call_id

    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", tool_call_id).strip("_")
    if (
        sanitized
        and len(sanitized) <= 64
        and _ANTHROPIC_TOOL_CALL_ID_PATTERN.fullmatch(sanitized)
    ):
        return sanitized

    digest = hashlib.sha256(tool_call_id.encode("utf-8")).hexdigest()[:16]
    prefix = sanitized[:40] if sanitized else "tool_call"
    prefix = re.sub(r"[^A-Za-z0-9_-]", "_", prefix).strip("_") or "tool_call"
    normalized = f"{prefix}_{digest}"[:64]
    return normalized.rstrip("_")


def _synthetic_tool_results(
    tool_calls: list[ToolCall],
    existing_tool_result_ids: set[str],
) -> list[ToolResultMessage]:
    return [
        ToolResultMessage(
            role="toolResult",
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=[TextPart(type="text", text=MISSING_TOOL_RESULT_TEXT)],
            is_error=True,
            timestamp=0.0,
            details={
                "synthetic": True,
                "reason": SYNTHETIC_TOOL_RESULT_REASON,
            },
        )
        for tool_call in tool_calls
        if tool_call.id not in existing_tool_result_ids
    ]
