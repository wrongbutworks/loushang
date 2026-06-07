"""Debug raw SSE lines from Kimi OpenAI-compatible chat completions."""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

BASE_URL = "https://api.moonshot.cn/v1"


def _resolve_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("KIMI_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY or KIMI_API_KEY before running this script.")
    return api_key


async def _main() -> None:
    headers = {"Authorization": f"Bearer {_resolve_api_key()}"}
    payload = {
        "model": "kimi-k2.5",
        "messages": [
            {
                "role": "system",
                "content": "你是 Kimi，由 Moonshot AI 提供的人工智能助手。",
            },
            {
                "role": "user",
                "content": "你好，我叫李雷，1+1等于多少？",
            },
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": 128,
    }

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        async with client.stream(
            "POST",
            "/chat/completions",
            json=payload,
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                print(repr(line))


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
