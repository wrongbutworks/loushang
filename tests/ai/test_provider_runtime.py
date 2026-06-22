from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from loushang.ai.options import CallOptions, RetryOptions
from loushang.ai.provider import ResolvedRequest
from loushang.ai.provider.errors import provider_error_part
from loushang.ai.provider.runtime import start_provider_runtime
from loushang.ai.providers.anthropic import AnthropicProvider
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.providers.openai_responses import OpenAIResponsesProvider


class _HTTPError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


@pytest.mark.parametrize(
    "provider_cls",
    (OpenAICompletionsProvider, OpenAIResponsesProvider, AnthropicProvider),
)
def test_builtin_adapters_expose_stream_raw_contract(provider_cls) -> None:
    provider = provider_cls()

    assert callable(getattr(provider, "stream_raw", None))
    assert "stream" not in provider_cls.__dict__


def test_provider_runtime_assembles_raw_parts() -> None:
    async def _parts():
        yield {"type": "response_start", "response_id": "resp_1"}
        yield {"type": "text_delta", "text": "hello"}
        yield {"type": "response_done"}

    async def _run():
        stream = start_provider_runtime(
            _parts,
            model=_model(),
            options=None,
            request=_request(),
        )
        return [event async for event in stream]

    events = asyncio.run(_run())

    assert [event["type"] for event in events] == [
        "start",
        "text_start",
        "text_delta",
        "text_end",
        "done",
    ]
    assert events[-1]["message"].content[0].text == "hello"


def test_provider_runtime_converts_adapter_exceptions_to_error_events() -> None:
    async def _parts():
        raise RuntimeError("adapter failed")
        yield {"type": "response_done"}

    async def _run():
        stream = start_provider_runtime(
            _parts,
            model=_model(),
            options=None,
            request=_request(),
        )
        return [event async for event in stream]

    events = asyncio.run(_run())

    assert [event["type"] for event in events] == ["error"]
    assert events[0]["error"].error_message == "adapter failed"
    assert events[0]["error_info"]["message"] == "adapter failed"


def test_provider_runtime_retries_retryable_exception_before_visible_output() -> None:
    attempts = 0
    trace_events: list[dict[str, object]] = []

    async def _parts():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _HTTPError("temporarily unavailable", 503)
        yield {"type": "response_start", "response_id": "resp_2"}
        yield {"type": "text_delta", "text": "recovered"}
        yield {"type": "response_done"}

    async def _run():
        stream = start_provider_runtime(
            _parts,
            model=_model(),
            options=CallOptions(
                retry=RetryOptions(max_attempts=2, max_delay_seconds=0),
                trace=trace_events.append,
            ),
            request=_request(),
        )
        return [event async for event in stream]

    events = asyncio.run(_run())

    assert attempts == 2
    assert [event["type"] for event in events] == [
        "start",
        "text_start",
        "text_delta",
        "text_end",
        "done",
    ]
    assert events[-1]["message"].content[0].text == "recovered"
    assert trace_events == [
        {
            "type": "runtime:retry",
            "attempt": 2,
            "maxAttempts": 2,
            "delayMs": 0,
            "reason": "service_unavailable",
            "statusCode": 503,
        }
    ]


def test_provider_runtime_retries_response_error_before_visible_output() -> None:
    attempts = 0

    async def _parts():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield provider_error_part(_HTTPError("rate limited", 429), source="openai")
            return
        yield {"type": "response_start", "response_id": "resp_3"}
        yield {"type": "text_delta", "text": "ok"}
        yield {"type": "response_done"}

    async def _run():
        stream = start_provider_runtime(
            _parts,
            model=_model(),
            options=CallOptions(retry=RetryOptions(max_attempts=2, max_delay_seconds=0)),
            request=_request(),
        )
        return [event async for event in stream]

    events = asyncio.run(_run())

    assert attempts == 2
    assert [event["type"] for event in events] == [
        "start",
        "text_start",
        "text_delta",
        "text_end",
        "done",
    ]
    assert events[-1]["message"].content[0].text == "ok"


def test_provider_runtime_does_not_retry_nonretryable_error_before_output() -> None:
    attempts = 0

    async def _parts():
        nonlocal attempts
        attempts += 1
        raise _HTTPError("unauthorized", 401)
        yield {"type": "response_done"}

    async def _run():
        stream = start_provider_runtime(
            _parts,
            model=_model(),
            options=CallOptions(retry=RetryOptions(max_attempts=2, max_delay_seconds=0)),
            request=_request(),
        )
        return [event async for event in stream]

    events = asyncio.run(_run())

    assert attempts == 1
    assert [event["type"] for event in events] == ["error"]
    assert events[0]["error_info"]["code"] == "authentication"
    assert events[0]["error_info"]["statusCode"] == 401


def test_provider_runtime_does_not_retry_after_visible_output() -> None:
    attempts = 0

    async def _parts():
        nonlocal attempts
        attempts += 1
        yield {"type": "response_start", "response_id": "resp_4"}
        yield {"type": "text_delta", "text": "partial"}
        raise _HTTPError("rate limited", 429)

    async def _run():
        stream = start_provider_runtime(
            _parts,
            model=_model(),
            options=CallOptions(retry=RetryOptions(max_attempts=2, max_delay_seconds=0)),
            request=_request(),
        )
        return [event async for event in stream]

    events = asyncio.run(_run())

    assert attempts == 1
    assert [event["type"] for event in events] == [
        "start",
        "text_start",
        "text_delta",
        "error",
    ]
    assert events[-1]["error"].content[0].text == "partial"
    assert events[-1]["error_info"]["statusCode"] == 429


def test_provider_runtime_uses_retry_after_delay() -> None:
    attempts = 0
    delays: list[float] = []

    async def _sleep(delay: float) -> None:
        delays.append(delay)

    async def _parts():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _HTTPError(
                "slow down",
                429,
                headers={"Retry-After": "1"},
            )
        yield {"type": "text_delta", "text": "done"}
        yield {"type": "response_done"}

    async def _run():
        stream = start_provider_runtime(
            _parts,
            model=_model(),
            options=CallOptions(retry=RetryOptions(max_attempts=2)),
            request=_request(),
            _sleep=_sleep,
            _jitter=lambda: 0.0,
        )
        return await stream.result()

    message = asyncio.run(_run())

    assert attempts == 2
    assert delays == [1.0]
    assert message.content[0].text == "done"


def test_provider_runtime_applies_backpressure_to_raw_source() -> None:
    produced = 0

    async def _parts():
        nonlocal produced
        yield {"type": "response_start", "response_id": "resp_backpressure"}
        for index in range(1000):
            produced += 1
            yield {"type": "text_delta", "text": str(index)}
        yield {"type": "response_done"}

    async def _run() -> int:
        stream = start_provider_runtime(
            _parts,
            model=_model(),
            options=None,
            request=_request(),
        )
        assert stream._queue.maxsize > 0
        await asyncio.sleep(0.05)
        produced_before_consume = produced
        await stream.aclose()
        return produced_before_consume

    produced_before_consume = asyncio.run(_run())

    assert 0 < produced_before_consume < 1000


def _model():
    return SimpleNamespace(id="model-a", provider_id="provider-a")


def _request() -> ResolvedRequest:
    return ResolvedRequest(
        provider="provider-a",
        endpoint="openai-responses",
        api="openai-responses",
        base_url=None,
    )
