"""Advanced offline trace schema and redaction example."""

from __future__ import annotations

import asyncio
import json

from loushang.ai import CallOptions, Model, RetryOptions, stream
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import ModelRegistry
from loushang.ai.trace import emit_trace


class _RetryableProviderError(Exception):
    status_code = 503

    def __init__(self) -> None:
        super().__init__("Provider temporarily unavailable.")
        self.headers = {"Retry-After": "0", "x-request-id": "req_trace_retry"}


class _TraceProvider:
    api = "anthropic-messages"

    def __init__(self) -> None:
        self.attempts = 0

    async def stream_raw(self, model, context, options, request):
        self.attempts += 1
        emit_trace(
            options,
            {
                "type": "sdk:client",
                "headers": {
                    "Authorization": "Bearer secret-token",
                    "x-api-key": "secret-key",
                    "anthropic-version": "2023-06-01",
                },
                "apiKey": "secret-key",
                "oauth": {"refresh_token": "refresh-secret"},
            },
        )
        if self.attempts == 1:
            raise _RetryableProviderError()
        yield {"type": "response_start", "response_id": "trace-demo"}
        yield {"type": "text_delta", "text": "trace recovered"}
        yield {"type": "response_done"}


async def inspect_trace_events() -> dict[str, object]:
    provider = _TraceProvider()
    trace_events: list[dict[str, object]] = []
    model_registry = _build_model_registry()
    model = model_registry.get_model("trace-demo", "anthropic-messages", "trace-demo")
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    event_stream = await stream(
        model,
        {"messages": []},
        CallOptions(
            retry=RetryOptions(max_attempts=2, max_delay_seconds=0),
            trace=trace_events.append,
        ),
        registry=registry,
    )
    message = await event_stream.result()
    sdk_client = next(event for event in trace_events if event["type"] == "sdk:client")
    retry = next(event for event in trace_events if event["type"] == "runtime:retry")
    return {
        "schemas": sorted({str(event["schema"]) for event in trace_events}),
        "eventTypes": [event["type"] for event in trace_events],
        "text": "".join(
            part.text for part in message.content if getattr(part, "type", None) == "text"
        ),
        "redaction": {
            "authorization": sdk_client["data"]["headers"]["Authorization"],
            "apiKey": sdk_client["data"]["apiKey"],
            "refreshToken": sdk_client["data"]["oauth"]["refresh_token"],
        },
        "retry": retry["data"],
    }


def main() -> None:
    print(json.dumps(asyncio.run(inspect_trace_events()), indent=2, sort_keys=True))


def _build_model() -> Model:
    return Model(
        id="trace-demo",
        provider="trace-demo",
        endpoint="anthropic-messages",
        capabilities=Capabilities(stream=True),
    )


def _build_model_registry() -> ModelRegistry:
    registry = ModelRegistry()
    registry.register_endpoint(
        "trace-demo",
        Endpoint(
            id="anthropic-messages",
            provider="trace-demo",
            api="anthropic-messages",
            models={"trace-demo": _build_model()},
        ),
    )
    return registry


if __name__ == "__main__":
    main()
