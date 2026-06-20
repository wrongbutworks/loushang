from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest

from loushang.ai.model import Capabilities, Endpoint, Model, ModelRegistry, Provider
from loushang.ai.provider import ResolvedRequest
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
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
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


def test_bedrock_converse_uses_resolved_capability_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    _patch_resolved_request(
        monkeypatch,
        max_tokens=None,
        capabilities=Capabilities(max_tokens=2048),
    )
    client = _FakeHttpClient()
    provider = BedrockConverseProvider(client=client)

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                _Model(max_tokens=1024),
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                None,
            )
        )
    )

    body = json.loads(client.content)
    assert body["inferenceConfig"]["maxTokens"] == 2048


def test_bedrock_converse_uses_real_resolved_request_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "catalog-access")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "catalog-secret")
    model = _bound_bedrock_model()
    client = _FakeHttpClient()
    provider = BedrockConverseProvider(client=client)

    asyncio.run(
        _collect_parts(
            provider._stream_raw_parts(
                model,
                {
                    "messages": [
                        UserMessage(role="user", content="hello", timestamp=0.0)
                    ]
                },
                None,
            )
        )
    )

    assert client.url == (
        "https://bedrock-runtime.us-west-2.amazonaws.com/model/"
        "anthropic.claude-sonnet-4-5-20250929-v1%3A0/converse"
    )
    assert "Credential=catalog-access/" in client.headers["authorization"]
    assert "/us-west-2/bedrock/aws4_request" in client.headers["authorization"]
    body = json.loads(client.content)
    assert body["inferenceConfig"]["maxTokens"] == 4096


async def _collect_parts(source) -> list[dict]:
    return [part async for part in source]


def _patch_resolved_request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_tokens: int | None = 1024,
    capabilities: Capabilities | None = None,
) -> None:
    def _resolve(provider_api, _model, *, options=None, request=None):
        if request is not None:
            if request.api != provider_api:
                raise ValueError(
                    f"Mismatched api: provider={provider_api!r} request.api={request.api!r}"
                )
            return request
        option_max_tokens = (
            getattr(options, "max_tokens", None) if options is not None else None
        )
        resolved_max_tokens = (
            max(1, option_max_tokens)
            if isinstance(option_max_tokens, int)
            else max_tokens
        )
        return ResolvedRequest(
            provider="bedrock",
            endpoint="bedrock-converse-stream",
            api="bedrock-converse-stream",
            base_url="https://bedrock-runtime.us-east-1.amazonaws.com",
            headers={},
            adapter_compat={},
            max_tokens=resolved_max_tokens,
            capabilities=capabilities or Capabilities(),
            reasoning_effort=None,
            upstream_model_id="anthropic.claude-sonnet-4-5-20250929-v1:0",
        )

    monkeypatch.setattr(
        "loushang.ai.providers.bedrock_converse.resolve_provider_request",
        _resolve,
    )


def _bound_bedrock_model() -> Model:
    endpoint = Endpoint(
        id="bedrock-converse-stream",
        provider="amazon-bedrock",
        api="bedrock-converse-stream",
        base_url="https://bedrock-runtime.us-west-2.amazonaws.com",
        models={
            "claude-public": Model(
                id="claude-public",
                provider="amazon-bedrock",
                endpoint="bedrock-converse-stream",
                capabilities=Capabilities(max_tokens=4096),
                upstream_id="anthropic.claude-sonnet-4-5-20250929-v1:0",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {
            "amazon-bedrock": Provider(
                id="amazon-bedrock", endpoints={endpoint.id: endpoint}
            )
        }
    )
    return registry.get_model(
        "amazon-bedrock", "bedrock-converse-stream", "claude-public"
    )


class _FakeHttpClient:
    url: str = ""
    content: str = ""
    headers: dict[str, str] = {}

    async def post(self, url: str, *, content: str, headers: dict[str, str]):
        self.url = url
        self.content = content
        self.headers = headers
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
