from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from loushang.ai.provider import ResolvedRequest
from loushang.ai.provider.runtime import start_provider_runtime
from loushang.ai.providers.anthropic import AnthropicProvider
from loushang.ai.providers.openai_completions import OpenAICompletionsProvider
from loushang.ai.providers.openai_responses import OpenAIResponsesProvider


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
            model=SimpleNamespace(id="model-a", provider_id="provider-a"),
            options=None,
            request=ResolvedRequest(
                provider="provider-a",
                endpoint="openai-responses",
                api="openai-responses",
                base_url=None,
            ),
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
            model=SimpleNamespace(id="model-a", provider_id="provider-a"),
            options=None,
            request=ResolvedRequest(
                provider="provider-a",
                endpoint="openai-responses",
                api="openai-responses",
                base_url=None,
            ),
        )
        return [event async for event in stream]

    events = asyncio.run(_run())

    assert [event["type"] for event in events] == ["error"]
    assert events[0]["error"].error_message == "adapter failed"
    assert events[0]["error_info"]["message"] == "adapter failed"
