"""Offline complete-call example."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable

from loushang.ai import CallOptions, Model, complete
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import ModelRegistry
from loushang.ai.providers.faux import FauxProvider

PROVIDER_ID = "faux"
ENDPOINT_ID = "anthropic-messages"
MODEL_ID = "faux-complete"
SYSTEM_PROMPT = "You are an offline example assistant."
USER_PROMPT = "请用两句话介绍你自己，并说明 1 + 1 等于几。"
MAX_TOKENS = 256


def _build_model() -> Model:
    return Model(
        id=MODEL_ID,
        provider=PROVIDER_ID,
        endpoint=ENDPOINT_ID,
        capabilities=Capabilities(stream=True),
    )


def _build_model_registry() -> ModelRegistry:
    registry = ModelRegistry()
    registry.register_endpoint(
        PROVIDER_ID,
        Endpoint(
            id=ENDPOINT_ID,
            provider=PROVIDER_ID,
            api="anthropic-messages",
            models={MODEL_ID: _build_model()},
        ),
    )
    return registry


def _build_provider_registry() -> ApiProviderRegistry:
    registry = ApiProviderRegistry()
    registry.register_api_provider(FauxProvider())
    return registry


def _build_context() -> dict[str, object]:
    return {
        "system_prompt": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": USER_PROMPT}],
    }


def _build_options() -> CallOptions:
    return CallOptions(max_output_tokens=MAX_TOKENS)


def _iter_text(parts: Iterable[object]) -> str:
    texts: list[str] = []
    for part in parts:
        if getattr(part, "type", None) == "text":
            texts.append(part.text)
    return "".join(texts)


async def inspect_complete() -> dict[str, object]:
    model = _build_model_registry().get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)
    message = await complete(
        model,
        _build_context(),
        _build_options(),
        registry=_build_provider_registry(),
    )
    return {
        "model": f"{model.provider_id}:{model.endpoint_id}:{model.id}",
        "responseId": message.response_id,
        "stopReason": message.stop_reason,
        "text": _iter_text(message.content),
    }


def main() -> None:
    print(json.dumps(asyncio.run(inspect_complete()), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
