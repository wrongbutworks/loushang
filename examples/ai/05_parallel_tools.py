"""Offline parallel tool-call assembly example."""

from __future__ import annotations

import asyncio
import json

from loushang.ai import CallOptions, Model, complete
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import ModelRegistry


class _ParallelToolProvider:
    api = "anthropic-messages"

    async def stream_raw(self, model, context, options, request):
        yield {"type": "response_start", "response_id": "parallel-tools-demo"}
        yield {"type": "tool_call_start", "id": "call_add", "name": "add", "index": 0}
        yield {"type": "tool_call_start", "id": "call_mul", "name": "multiply", "index": 1}
        yield {
            "type": "tool_call_args_delta",
            "tool_call_id": "call_add",
            "delta": '{"a":',
        }
        yield {"type": "tool_call_args_delta", "index": 1, "delta": '{"x":'}
        yield {"type": "tool_call_args_delta", "index": 0, "delta": "2}"}
        yield {"type": "tool_call_args_delta", "tool_call_id": "call_mul", "delta": "3}"}
        yield {"type": "tool_call_done", "index": 1}
        yield {"type": "tool_call_done", "tool_call_id": "call_add"}
        yield {"type": "stop_reason", "stop_reason": "toolUse"}
        yield {"type": "response_done"}


async def inspect_parallel_tools() -> dict[str, object]:
    model_registry = _build_model_registry()
    model = model_registry.get_model(
        "parallel-tools-demo",
        "anthropic-messages",
        "parallel-tools-demo",
    )
    registry = ApiProviderRegistry()
    registry.register_api_provider(_ParallelToolProvider())
    message = await complete(
        model,
        {"messages": []},
        CallOptions(),
        registry=registry,
    )
    return {
        "stopReason": message.stop_reason,
        "toolCalls": [
            {
                "id": part.id,
                "name": part.name,
                "arguments": part.arguments,
            }
            for part in message.content
            if getattr(part, "type", None) == "toolCall"
        ],
    }


def main() -> None:
    print(json.dumps(asyncio.run(inspect_parallel_tools()), indent=2, sort_keys=True))


def _build_model() -> Model:
    return Model(
        id="parallel-tools-demo",
        provider="parallel-tools-demo",
        endpoint="anthropic-messages",
        capabilities=Capabilities(stream=True, tool_use=True),
    )


def _build_model_registry() -> ModelRegistry:
    registry = ModelRegistry()
    registry.register_endpoint(
        "parallel-tools-demo",
        Endpoint(
            id="anthropic-messages",
            provider="parallel-tools-demo",
            api="anthropic-messages",
            models={"parallel-tools-demo": _build_model()},
        ),
    )
    return registry


if __name__ == "__main__":
    main()
