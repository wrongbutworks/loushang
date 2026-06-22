"""Kimi 工具调用示例。"""

from __future__ import annotations

import asyncio
import os
import sys

from loushang.ai import (
    CallOptions,
    TextPart,
    Tool,
    ToolCall,
    ToolResultMessage,
    get_model,
)
from loushang.ai.tool import validate_tool_arguments, validate_tool_arguments_result

API_KEY = ""
PROVIDER_ID = "moonshot"
ENDPOINT_ID = "openai-completions"
MODEL_ID = "kimi-k2.5"
USER_PROMPT = "只调用工具，不要心算：使用 add 计算 78 + 35，并返回结果。"
MAX_TOKENS = 1024


def _resolve_api_key() -> str:
    value = API_KEY or os.getenv("MOONSHOT_API_KEY")
    if value:
        return value
    raise RuntimeError(
        "Set API_KEY at the top of this file, or export MOONSHOT_API_KEY."
    )


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


def _build_options(api_key: str) -> CallOptions:
    return CallOptions(api_key=api_key, max_output_tokens=MAX_TOKENS)


async def main() -> None:
    api_key = _resolve_api_key()
    model = get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
    tool = _add_tool()
    tools = [_tool_payload(tool)]

    first = await model.complete(
        {
            "system_prompt": "当需要外部计算时，请优先调用工具；收到工具结果后请用中文一句话回答。",
            "messages": [{"role": "user", "content": USER_PROMPT}],
            "tools": tools,
        },
        _build_options(api_key),
    )

    tool_call = next(
        (part for part in first.content if getattr(part, "type", None) == "toolCall"),
        None,
    )
    if tool_call is None:
        raise RuntimeError("Model did not emit a structured tool call.")

    args = validate_tool_arguments(tool, tool_call)
    result_text = str(args["a"] + args["b"])

    print(
        f"TOOL_CALL id={tool_call.id!r} "
        f"name={tool_call.name!r} arguments={tool_call.arguments!r}"
    )

    second = await model.complete(
        {
            "system_prompt": "你已经拿到工具结果，请用中文一句话给出最终答案。",
            "messages": [
                {"role": "user", "content": USER_PROMPT},
                first,
                ToolResultMessage(
                    role="toolResult",
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    content=[TextPart(type="text", text=result_text)],
                    is_error=False,
                    timestamp=0.0,
                ),
            ],
            "tools": tools,
        },
        _build_options(api_key),
    )

    for part in second.content:
        if getattr(part, "type", None) == "text":
            print(part.text, end="")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # pragma: no cover - example path
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
