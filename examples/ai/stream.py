"""Kimi 流式示例。"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterable

from loushang.ai import OpenAICompletionsOptions, get_model, stream


API_KEY = ""
PROVIDER_ID = "moonshot"
ENDPOINT_ID = "openai-completions"
MODEL_ID = "kimi-k2.5"
SYSTEM_PROMPT = "你是 Kimi，由 Moonshot AI 提供。回答要简洁、准确，优先使用中文。"
USER_PROMPT = "请用两句话介绍你自己，并说明 1 + 1 等于几。"
MAX_TOKENS = 256


def _resolve_api_key() -> str:
    value = API_KEY or os.getenv("MOONSHOT_API_KEY")
    if value:
        return value
    raise RuntimeError("Set API_KEY at the top of this file, or export MOONSHOT_API_KEY.")


def _build_context() -> dict:
    return {
        "system_prompt": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": USER_PROMPT}],
    }


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
    event_stream = await stream(
        model,
        _build_context(),
        _build_options(_resolve_api_key()),
    )

    print(f"MODEL {model.provider_id}:{model.endpoint_id}:{model.id}")
    async for event in event_stream:
        line = f"EVENT {event['type']}"
        if event["type"] == "text_delta":
            line += f" text={event['delta']!r}"
        print(line)

    message = await event_stream.result()
    print(f"FINAL stop_reason={message.stop_reason!r}")
    print(f"FINAL response_id={message.response_id!r}")
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
