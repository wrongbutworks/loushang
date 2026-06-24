from __future__ import annotations

from loushang.ai.types import AssistantMessage, Usage


def usage_from_message(
    message: AssistantMessage,
) -> Usage:
    return message.usage


def usage_payload(usage: Usage | None) -> dict[str, object]:
    if usage is None:
        return {
            "present": False,
            "input": None,
            "output": None,
            "cacheRead": None,
            "cacheWrite": None,
            "totalTokens": None,
            "cost": None,
        }
    return {
        "present": True,
        "input": usage.input,
        "output": usage.output,
        "cacheRead": usage.cache_read,
        "cacheWrite": usage.cache_write,
        "totalTokens": usage.total_tokens,
        "cost": usage.cost,
    }
