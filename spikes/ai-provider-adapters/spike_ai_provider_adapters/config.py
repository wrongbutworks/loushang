from __future__ import annotations

import os

from .types import Context, Model


def resolve_api_key() -> str:
    for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "KIMI_API_KEY"):
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError("No API key found in ANTHROPIC_AUTH_TOKEN, ANTHROPIC_API_KEY, or KIMI_API_KEY")


def build_real_model() -> Model:
    return Model(
        id="kimi-k2.5",
        name="kimi-k2.5",
        api="anthropic-messages",
        provider="anthropic",
        base_url="https://api.moonshot.cn/anthropic",
        reasoning=False,
        input=["text"],
        context_window=200000,
        max_tokens=8192,
        cost={"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        headers={},
    )


def build_mock_model() -> Model:
    return Model(
        id="faux-mock",
        name="faux-mock",
        api="anthropic-messages",
        provider="faux",
        base_url="http://localhost",
        reasoning=False,
        input=["text"],
        context_window=8192,
        max_tokens=8192,
        cost={"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        headers={},
    )


def build_mock_context() -> Context:
    return Context(
        system_prompt="You are a concise assistant.",
        messages=[{"role": "user", "content": "Say hello in one sentence.", "timestamp": 0}],
        tools=[],
    )


def build_real_context() -> Context:
    return Context(
        system_prompt="You are a concise assistant.",
        messages=[{"role": "user", "content": "Reply with a short hello and mention the provider name once.", "timestamp": 0}],
        tools=[],
    )

