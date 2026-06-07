"""Kimi 工具调用示例。"""

from __future__ import annotations

import asyncio
import os
import sys

from loushang.ai import OpenAICompletionsOptions, TextPart, ToolResultMessage, get_model

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
    raise RuntimeError("Set API_KEY at the top of this file, or export MOONSHOT_API_KEY.")


def _build_tools() -> list[dict]:
    return [
        {
            "name": "add",
            "description": "Return the sum of two numbers a and b.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "first number"},
                    "b": {"type": "number", "description": "second number"},
                },
                "required": ["a", "b"],
                "additionalProperties": False,
            },
        }
    ]


def _build_options(api_key: str) -> OpenAICompletionsOptions:
    return OpenAICompletionsOptions(api_key=api_key, max_tokens=MAX_TOKENS)


async def main() -> None:
    api_key = _resolve_api_key()
    model = get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
    tools = _build_tools()

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

    args = getattr(tool_call, "arguments", {}) or {}
    a = args.get("a", 0)
    b = args.get("b", 0)
    result_text = str(
        (a if isinstance(a, (int, float)) else 0)
        + (b if isinstance(b, (int, float)) else 0)
    )

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
