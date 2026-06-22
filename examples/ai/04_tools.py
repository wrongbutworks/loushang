"""Offline tool-call and tool-result handling example."""

from __future__ import annotations

import json

from loushang.ai import TextPart, Tool, ToolCall, ToolResultMessage
from loushang.ai.tool import validate_tool_arguments, validate_tool_arguments_result

USER_PROMPT = "只调用工具，不要心算：使用 add 计算 78 + 35，并返回结果。"


def _add_tool() -> Tool:
    return Tool(
        name="add",
        description="Return the sum of two numbers a and b.",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "first number"},
                "b": {"type": "number", "description": "second number"},
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    )


def _tool_payload(tool: Tool) -> dict[str, object]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
    }


def _build_tools() -> list[dict[str, object]]:
    return [_tool_payload(_add_tool())]


def _offline_tool_call() -> ToolCall:
    return ToolCall(
        type="toolCall",
        id="call_add",
        name="add",
        arguments={"a": 78, "b": 35},
    )


def _tool_result_message(tool_call: ToolCall, result_text: str) -> ToolResultMessage:
    return ToolResultMessage(
        role="toolResult",
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=[TextPart(type="text", text=result_text)],
        is_error=False,
        timestamp=0.0,
    )


def _inspect_tool_validation() -> dict[str, object]:
    tool = _add_tool()
    strict_call = ToolCall(
        type="toolCall",
        id="tc_strict",
        name="add",
        arguments={"a": 2, "b": 3},
    )
    coerce_call = ToolCall(
        type="toolCall",
        id="tc_coerce",
        name="add",
        arguments={"a": "2", "b": "3"},
    )

    strict_arguments = validate_tool_arguments(tool, strict_call)
    try:
        validate_tool_arguments(tool, coerce_call)
    except ValueError as error:
        strict_error = str(error).splitlines()[0]
    else:  # pragma: no cover - defensive example guard
        strict_error = ""

    coerce_result = validate_tool_arguments_result(
        tool,
        coerce_call,
        validation_policy="coerce",
    )
    return {
        "strict": strict_arguments,
        "strictError": strict_error,
        "coerce": coerce_result.arguments,
        "diagnostics": [
            {
                "code": diagnostic.code,
                "path": diagnostic.path,
                "fromType": diagnostic.from_type,
                "toType": diagnostic.to_type,
            }
            for diagnostic in coerce_result.diagnostics
        ],
    }


def inspect_tools() -> dict[str, object]:
    tool = _add_tool()
    tool_call = _offline_tool_call()
    args = validate_tool_arguments(tool, tool_call)
    result_text = str(args["a"] + args["b"])
    tool_result = _tool_result_message(tool_call, result_text)
    return {
        "toolCall": {
            "id": tool_call.id,
            "name": tool_call.name,
            "arguments": tool_call.arguments,
        },
        "toolResult": "".join(part.text for part in tool_result.content),
        "validation": _inspect_tool_validation(),
        "finalText": f"工具返回 {result_text}，所以答案是 {result_text}。",
    }


def main() -> None:
    print(json.dumps(inspect_tools(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
