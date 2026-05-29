from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from loushang.ai.api.streaming import stream
from loushang.ai.context import NORMALIZED_CONTEXT_MARKER
from loushang.ai.options import StreamOptions
from loushang.ai.types import AssistantMessage, ToolCall, Usage, UserMessage


@dataclass
class _Capabilities:
    supports_image_input: bool = False
    supports_thinking: bool = False


@dataclass
class _Model:
    id: str = "test-model"
    capabilities: _Capabilities = field(default_factory=_Capabilities)


class _Registry:
    def __init__(self, provider) -> None:
        self._provider = provider

    def get_api_provider(self, _api: str):
        return self._provider


class _Provider:
    def __init__(self) -> None:
        self.context = None
        self.options = None

    async def stream(self, model, context, options):
        self.context = context
        self.options = options
        return _DoneStream()

    async def stream_simple(self, model, context, options):
        return await self.stream(model, context, options)


class _DoneStream:
    def __aiter__(self):
        async def _iterate():
            if False:
                yield None

        return _iterate()

    async def result(self):
        return None


def test_stream_exposes_pairing_mode_through_public_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "loushang.ai.api.streaming.resolve_model_api", lambda _model: "faux"
    )
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)
    assistant = AssistantMessage(
        role="assistant",
        content=[
            ToolCall(type="toolCall", id="call_1", name="calc", arguments={"x": 1})
        ],
        api="openai-responses",
        provider="openai",
        model="gpt-test",
        response_id="resp_1",
        usage=Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total_tokens=0,
            cost={},
        ),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )

    with pytest.raises(ValueError, match="Missing tool results before next message"):
        asyncio.run(
            stream(
                _Model(),
                {
                    "messages": [
                        assistant,
                        UserMessage(role="user", content="next", timestamp=0.0),
                    ]
                },
                StreamOptions(pairing_mode="strict"),
                registry=registry,
            )
        )


def test_stream_passes_normalized_context_to_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "loushang.ai.api.streaming.resolve_model_api", lambda _model: "faux"
    )
    monkeypatch.setattr("loushang.ai.messages.resolve_model_api", lambda _model: "faux")
    monkeypatch.setattr(
        "loushang.ai.tool.transform.resolve_model_api", lambda _model: "faux"
    )
    provider = _Provider()
    registry = _Registry(provider)

    asyncio.run(
        stream(
            _Model(),
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            StreamOptions(),
            registry=registry,
        )
    )

    assert provider.context[NORMALIZED_CONTEXT_MARKER] is True
    assert provider.context["messages"][0].role == "user"
