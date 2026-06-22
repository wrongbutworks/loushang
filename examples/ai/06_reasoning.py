"""Offline simple reasoning example."""

from __future__ import annotations

import asyncio
import json

from loushang.ai import Model, SimpleCallOptions, stream_simple
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import get_default_model_registry
from loushang.ai.providers.faux import FauxProvider


def _build_model() -> Model:
    return Model(
        id="faux-reasoning",
        provider="faux",
        endpoint="anthropic-messages",
        capabilities=Capabilities(stream=True, reasoning=True),
    )


def _register_model() -> None:
    get_default_model_registry().register_endpoint(
        "faux",
        Endpoint(
            id="anthropic-messages",
            provider="faux",
            api="anthropic-messages",
            models={"faux-reasoning": _build_model()},
        ),
    )


async def inspect_reasoning() -> dict[str, object]:
    _register_model()
    registry = ApiProviderRegistry()
    registry.register_api_provider(FauxProvider())
    event_stream = await stream_simple(
        _build_model(),
        {"messages": []},
        SimpleCallOptions(
            reasoning="medium",
            thinking_budgets={"medium": 2048},
        ),
        registry=registry,
    )
    events: list[dict[str, str]] = []
    async for event in event_stream:
        event_type = event["type"]
        if event_type == "thinking_delta":
            part = event["partial"].content[event["content_index"]]
            events.append({"type": event_type, "thinking": part.thinking})
        elif event_type == "text_delta":
            events.append({"type": event_type, "text": event["delta"]})
    message = await event_stream.result()
    return {
        "reasoning": "medium",
        "budgetTokens": 2048,
        "events": events,
        "stopReason": message.stop_reason,
    }


def main() -> None:
    print(json.dumps(asyncio.run(inspect_reasoning()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
