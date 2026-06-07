"""Debug mapped raw parts from Kimi OpenAI-compatible chat completions."""

from __future__ import annotations

import asyncio
import os
import sys

from loushang.ai.model_registry import ModelDefinition
from loushang.ai.providers.openai_chat_completions_httpx import (
    OpenAIChatCompletionsHttpxProvider,
)

BASE_URL = "https://api.moonshot.cn/v1"


class _Options:
    def __init__(self, *, api_key: str, max_tokens: int) -> None:
        self.api_key = api_key
        self.max_tokens = max_tokens


def _resolve_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("KIMI_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY or KIMI_API_KEY before running this script.")
    return api_key


async def _main() -> None:
    provider = OpenAIChatCompletionsHttpxProvider(base_url=BASE_URL)
    model = ModelDefinition(id="kimi-k2.5", api="openai-completions", provider="openai")
    context = {
        "messages": [
            {"role": "system", "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。"},
            {"role": "user", "content": "你好，我叫李雷，1+1等于多少？"},
        ]
    }
    options = _Options(api_key=_resolve_api_key(), max_tokens=128)

    async for part in provider._stream_raw_parts(model, context, options):
        print(part)


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
