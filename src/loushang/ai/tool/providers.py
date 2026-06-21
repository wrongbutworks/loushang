from __future__ import annotations

import json
from typing import Any

from loushang.ai.types import (
    AssistantMessage,
    ImagePart,
    TextPart,
    Tool,
    ToolCall,
    ToolResultMessage,
)

_JSON_SCHEMA_META_DECLARATIONS = {
    "$schema",
    "$id",
    "$anchor",
    "$dynamicAnchor",
    "$vocabulary",
    "$comment",
    "$defs",
    "definitions",
}


def sanitize_tool_parameters(parameters: object) -> object:
    if isinstance(parameters, dict):
        return {
            key: sanitize_tool_parameters(value)
            for key, value in parameters.items()
            if key not in _JSON_SCHEMA_META_DECLARATIONS
        }
    if isinstance(parameters, list):
        return [sanitize_tool_parameters(item) for item in parameters]
    return parameters


def to_anthropic_tools(tools: list[Tool]) -> list[dict]:
    payload: list[dict] = []
    for tool in tools:
        payload.append(
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": sanitize_tool_parameters(tool.parameters),
            }
        )
    return payload


def to_openai_completions_tools(tools: list[Tool]) -> list[dict]:
    payload: list[dict] = []
    for tool in tools:
        payload.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": sanitize_tool_parameters(tool.parameters),
                },
            }
        )
    return payload


def to_openai_responses_tools(tools: list[Tool]) -> list[dict]:
    payload: list[dict] = []
    for tool in tools:
        payload.append(
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": sanitize_tool_parameters(tool.parameters),
            }
        )
    return payload


def to_openai_completions_assistant_message(message: AssistantMessage) -> dict:
    text_parts, tool_calls = _openai_assistant_parts(message)
    payload: dict = {
        "role": "assistant",
        "content": "\n".join(text_parts) if text_parts else None,
    }
    if tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(tool_call.arguments),
                },
            }
            for tool_call in tool_calls
        ]
    return payload


def to_openai_responses_assistant_input(message: AssistantMessage) -> list[dict]:
    text_parts, tool_calls = _openai_assistant_parts(message)
    payload: list[dict] = []
    if text_parts:
        payload.append({"role": "assistant", "content": "\n".join(text_parts)})
    payload.extend(
        {
            "type": "function_call",
            "call_id": tool_call.id,
            "name": tool_call.name,
            "arguments": json.dumps(tool_call.arguments),
        }
        for tool_call in tool_calls
    )
    return payload


def to_openai_completions_tool_result_message(
    message: ToolResultMessage,
    *,
    include_name: bool = False,
) -> dict:
    payload = {
        "role": "tool",
        "tool_call_id": message.tool_call_id,
        "content": _openai_tool_result_text(message),
    }
    if include_name and message.tool_name:
        payload["name"] = message.tool_name
    return payload


def to_openai_responses_tool_result_input(message: ToolResultMessage) -> dict:
    image_parts = _openai_responses_tool_result_images(message)
    if image_parts:
        output_parts: list[dict[str, Any]] = [
            {"type": "input_text", "text": text}
            for text in _openai_tool_result_text_parts(message)
        ]
        output_parts.extend(image_parts)
        output: str | list[dict[str, Any]] = output_parts
    else:
        output = _openai_tool_result_text(message)
    return {
        "type": "function_call_output",
        "call_id": message.tool_call_id,
        "output": output,
    }


def _openai_tool_result_text(message: ToolResultMessage) -> str:
    text = "\n".join(_openai_tool_result_text_parts(message))
    if text:
        return text
    if any(_part_type(part) == "image" for part in message.content):
        return "(see attached image)"
    return "No result provided"


def _openai_tool_result_text_parts(message: ToolResultMessage) -> list[str]:
    return [
        text
        for part in message.content
        if _part_type(part) == "text"
        and isinstance((text := _part_text(part)), str)
        and text.strip()
    ]


def _openai_responses_tool_result_images(message: ToolResultMessage) -> list[dict[str, Any]]:
    image_parts: list[dict[str, Any]] = []
    for part in message.content:
        if _part_type(part) != "image":
            continue
        data = _part_data(part)
        mime_type = _part_mime_type(part)
        if isinstance(data, str) and data and isinstance(mime_type, str) and mime_type:
            image_parts.append(
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": f"data:{mime_type};base64,{data}",
                }
            )
    return image_parts


def _part_type(part: TextPart | ImagePart) -> str | None:
    return getattr(part, "type", None)


def _part_text(part: TextPart | ImagePart) -> str | None:
    return getattr(part, "text", None)


def _part_data(part: TextPart | ImagePart) -> str | None:
    return getattr(part, "data", None)


def _part_mime_type(part: TextPart | ImagePart) -> str | None:
    return getattr(part, "mime_type", None)


def _openai_assistant_parts(
    message: AssistantMessage,
) -> tuple[list[str], list[ToolCall]]:
    text_parts = [part.text for part in message.content if isinstance(part, TextPart)]
    tool_calls = [part for part in message.content if isinstance(part, ToolCall)]
    unsupported = [
        part for part in message.content if not isinstance(part, TextPart | ToolCall)
    ]
    if unsupported:
        raise ValueError(
            "openai providers currently support text/tool-call assistant message content"
        )
    return text_parts, tool_calls
