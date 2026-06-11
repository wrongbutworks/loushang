from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest

from loushang.ai.providers.bedrock_converse import BedrockConverseProvider
from loushang.ai.types import UserMessage


def test_bedrock_converse_uses_upstream_model_id_and_maps_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    _patch_resolved_request(monkeypatch)
    client = _FakeHttpClient()
    provider = BedrockConverseProvider(client=client)

    parts = asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(),
                {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
                None,
            )
        )
    )

    assert client.url.endswith(
        "/model/anthropic.claude-sonnet-4-5-20250929-v1%3A0/converse"
    )
    body = json.loads(client.content)
    assert body["messages"] == [{"role": "user", "content": [{"text": "hello"}]}]
    assert {"type": "text_delta", "text": "hi"} in parts
    assert {"type": "stop_reason", "stop_reason": "stop"} in parts


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


def _patch_resolved_request(monkeypatch: pytest.MonkeyPatch) -> None:
    def _resolve(_model, options=None):
        return type(
            "Resolved",
            (),
            {
                "api": "bedrock-converse-stream",
                "headers": {},
                "base_url": "https://bedrock-runtime.us-east-1.amazonaws.com",
                "compat": {
                    "upstreamModelId": (
                        "anthropic.claude-sonnet-4-5-20250929-v1:0"
                    )
                },
                "max_tokens": 1024,
                "reasoning_effort": None,
            },
        )()

    monkeypatch.setattr(
        "loushang.ai.providers.bedrock_converse.resolve_request_for_model",
        _resolve,
    )


class _FakeHttpClient:
    url: str = ""
    content: str = ""

    async def post(self, url: str, *, content: str, headers: dict[str, str]):
        self.url = url
        self.content = content
        assert "authorization" in headers
        return _FakeResponse()


class _FakeResponse:
    headers = {"x-amzn-requestid": "req_1"}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "output": {
                "message": {
                    "content": [{"text": "hi"}],
                }
            },
            "usage": {"inputTokens": 1, "outputTokens": 1},
            "stopReason": "end_turn",
        }


@dataclass(frozen=True)
class _Model:
    id: str = "anthropic.claude-sonnet-4-5-20250929-v1_0"
    reasoning: bool = False
    input: tuple[str, ...] = ("text", "image")
    max_tokens: int | None = 4096
    headers: dict[str, str] = field(default_factory=dict)
    compat: dict[str, object] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    provider_id: str = "amazon-bedrock"
    endpoint_id: str = "bedrock-converse-stream"
