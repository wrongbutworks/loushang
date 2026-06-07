"""Kimi 显式 Context 类型示例。"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterable

from loushang.ai import (
    Context,
    OpenAICompletionsOptions,
    Tool,
    UserMessage,
    complete,
    get_model,
)

API_KEY = ""
PROVIDER_ID = "moonshot"
ENDPOINT_ID = "openai-completions"
MODEL_ID = "kimi-k2.5"
MAX_TOKENS = 512


def _resolve_api_key() -> str:
    value = API_KEY or os.getenv("MOONSHOT_API_KEY")
    if value:
        return value
    raise RuntimeError("Set API_KEY at the top of this file, or export MOONSHOT_API_KEY.")


def _build_context() -> Context:
    return Context(
        system_prompt=(
            "你是 Kimi。优先直接回答用户问题；只有在用户明确要求外部工具时才调用工具。"
        ),
        messages=[
            UserMessage(
                role="user",
                content="请用两句话介绍你自己，并说明 1 + 1 等于几。不要调用工具。",
                timestamp=0.0,
            )
        ],
        tools=[
            Tool(
                name="add",
                description="Return the sum of two numbers a and b.",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["a", "b"],
                    "additionalProperties": False,
                },
            )
        ],
    )


def _build_options(api_key: str) -> OpenAICompletionsOptions:
    return OpenAICompletionsOptions(api_key=api_key, max_tokens=MAX_TOKENS)


def _iter_text(parts: Iterable[object]) -> str:
    texts: list[str] = []
    for part in parts:
        if getattr(part, "type", None) == "text":
            texts.append(part.text)
    return "".join(texts)


async def main() -> None:
    model = get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
    message = await complete(
        model,
        _build_context(),
        _build_options(_resolve_api_key()),
    )

    print(f"MODEL {model.provider_id}:{model.endpoint_id}:{model.id}")
    print(f"FINAL stop_reason={message.stop_reason!r}")
    print(f"FINAL text={_iter_text(message.content)!r}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # pragma: no cover - example path
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
