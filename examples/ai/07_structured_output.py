"""Offline structured output contract example."""

from __future__ import annotations

import asyncio
import json

from loushang.ai import CallOptions, Model, StructuredOutputOptions, complete_structured
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import ModelRegistry

ANSWER_SCHEMA = {
    "title": "Answer",
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "score": {"type": "integer"},
    },
    "required": ["answer", "score"],
    "additionalProperties": False,
}


class _StructuredProvider:
    api = "openai-responses"

    async def stream_raw(self, model, context, options, request):
        del model, context, request
        assert isinstance(options.output, StructuredOutputOptions)
        yield {"type": "response_start", "response_id": "structured-demo"}
        yield {"type": "text_delta", "text": '{"answer":"Paris","score":10}'}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


async def inspect_structured_output() -> dict[str, object]:
    model_registry = _build_model_registry()
    model = model_registry.get_model(
        "structured-output-demo",
        "openai-responses",
        "structured-output-demo",
    )
    registry = ApiProviderRegistry()
    registry.register_api_provider(_StructuredProvider())
    result = await complete_structured(
        model,
        {"messages": [{"role": "user", "content": "Return the answer as JSON."}]},
        StructuredOutputOptions(mode="json_schema", schema=ANSWER_SCHEMA),
        options=CallOptions(),
        registry=registry,
    )
    return {
        "responseId": result.raw.response_id,
        "stopReason": result.raw.stop_reason,
        "parsed": result.parsed,
    }


def main() -> None:
    print(
        json.dumps(asyncio.run(inspect_structured_output()), indent=2, sort_keys=True)
    )


def _build_model() -> Model:
    return Model(
        id="structured-output-demo",
        provider="structured-output-demo",
        endpoint="openai-responses",
        capabilities=Capabilities(stream=True, structured_output=True),
    )


def _build_model_registry() -> ModelRegistry:
    registry = ModelRegistry()
    registry.register_endpoint(
        "structured-output-demo",
        Endpoint(
            id="openai-responses",
            provider="structured-output-demo",
            api="openai-responses",
            models={"structured-output-demo": _build_model()},
        ),
    )
    return registry


if __name__ == "__main__":
    main()
