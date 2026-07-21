"""Run API-key environment and explicit-auth calls through ProviderRequest."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

from loushang.ai import ApiKeyAuth, CallOptions, complete
from loushang.ai.advanced.registry import (
    clear_api_providers,
    register_api_provider,
    reset_api_providers,
)
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.model import Auth, Capabilities, Model
from loushang.ai.provider import ProviderRequest

ENV_NAME = "LOUSHANG_AUTH_EXAMPLE_API_KEY"


class _RecordingProvider:
    api = "auth-example-api-key"

    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []

    async def invoke_raw(self, request: ProviderRequest) -> AsyncIterator[RawPart]:
        self.requests.append(request)
        yield {"type": "response_start", "response_id": "auth-example"}
        yield {"type": "text_delta", "text": "ok"}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


async def run() -> dict[str, object]:
    provider = _RecordingProvider()
    model = Model(
        id="api-key-example",
        provider="example",
        endpoint="api-key",
        api=provider.api,
        base_url="https://offline.example/v1",
        auth=Auth(kind="apiKey", api_key_env=ENV_NAME),
        capabilities=Capabilities(stream=True),
    )
    previous = os.environ.get(ENV_NAME)
    os.environ[ENV_NAME] = "environment-secret"
    clear_api_providers()
    register_api_provider(provider)
    try:
        await complete(
            model,
            {"messages": [{"role": "user", "content": "environment"}]},
        )
        await complete(
            model,
            {"messages": [{"role": "user", "content": "explicit"}]},
            CallOptions(auth=ApiKeyAuth("explicit-secret")),
        )
    finally:
        reset_api_providers()
        if previous is None:
            os.environ.pop(ENV_NAME, None)
        else:
            os.environ[ENV_NAME] = previous

    expected = ["Bearer environment-secret", "Bearer explicit-secret"]
    actual = [request.headers.get("Authorization") for request in provider.requests]
    return {
        "calls": len(provider.requests),
        "environmentResolved": actual[0] == expected[0],
        "explicitResolved": actual[1] == expected[1],
        "requestAuthTypes": [
            type(request.options.auth).__name__ for request in provider.requests
        ],
    }


def main() -> None:
    print(json.dumps(asyncio.run(run()), sort_keys=True))


if __name__ == "__main__":
    main()
