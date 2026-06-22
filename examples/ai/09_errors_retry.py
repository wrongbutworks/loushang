"""Offline error serialization and retry example."""

from __future__ import annotations

import asyncio
import json

from loushang.ai import AIError, AIErrorInfo, CallOptions, Model, RetryOptions, stream
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.model import Capabilities, Endpoint
from loushang.ai.model.registry import get_default_model_registry


class _RetryableProviderError(Exception):
    status_code = 503

    def __init__(self) -> None:
        super().__init__("Provider temporarily unavailable.")
        self.headers = {"Retry-After": "0"}


class _FlakyProvider:
    api = "anthropic-messages"

    def __init__(self) -> None:
        self.attempts = 0

    async def stream_raw(self, model, context, options, request):
        self.attempts += 1
        if self.attempts == 1:
            raise _RetryableProviderError()
        yield {"type": "response_start", "response_id": "retry-demo"}
        yield {"type": "text_delta", "text": "retry recovered"}
        yield {"type": "response_done"}


def inspect_error_serialization() -> dict[str, object]:
    error = AIError(
        AIErrorInfo(
            code="authentication",
            message="Missing API key.",
            source="client",
            retryable=False,
            provider="moonshot",
            endpoint="openai-completions",
            model="kimi-k2.5",
            details={
                "hint": "Set MOONSHOT_API_KEY.",
                "Authorization": "Bearer secret-token",
                "nested": {"refresh_token": "refresh-secret"},
            },
        )
    )
    return error.to_dict()


async def inspect_retry_policy() -> dict[str, object]:
    provider = _FlakyProvider()
    trace_events: list[dict[str, object]] = []
    _register_model()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    event_stream = await stream(
        _build_model(),
        {"messages": []},
        CallOptions(
            retry=RetryOptions(max_attempts=2, max_delay_seconds=0),
            trace=trace_events.append,
        ),
        registry=registry,
    )
    message = await event_stream.result()
    return {
        "attempts": provider.attempts,
        "text": "".join(
            part.text for part in message.content if getattr(part, "type", None) == "text"
        ),
        "trace": trace_events,
    }


def inspect_errors_retry() -> dict[str, object]:
    return {
        "error": inspect_error_serialization(),
        "retry": asyncio.run(inspect_retry_policy()),
    }


def main() -> None:
    print(json.dumps(inspect_errors_retry(), indent=2, sort_keys=True))


def _build_model() -> Model:
    return Model(
        id="retry-demo",
        provider="retry-demo",
        endpoint="anthropic-messages",
        capabilities=Capabilities(stream=True),
    )


def _register_model() -> None:
    get_default_model_registry().register_endpoint(
        "retry-demo",
        Endpoint(
            id="anthropic-messages",
            provider="retry-demo",
            api="anthropic-messages",
            models={"retry-demo": _build_model()},
        ),
    )


if __name__ == "__main__":
    main()
