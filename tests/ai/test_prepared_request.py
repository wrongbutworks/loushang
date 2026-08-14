from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from loushang.ai.context import NormalizedContext
from loushang.ai.errors import AIProviderError
from loushang.ai.model import Auth, Capabilities, Model
from loushang.ai.options import CallOptions, RetryOptions
from loushang.ai.prepared_request import (
    PreparedModelRequest,
    PreparedRequestAdapter,
)
from loushang.ai.protocols.anthropic_messages import AnthropicMessagesAdapter
from loushang.ai.protocols.openai_chat_completions import OpenAIChatCompletionsAdapter
from loushang.ai.protocols.openai_responses import OpenAIResponsesAdapter
from loushang.ai.provider import ProviderRequest
from loushang.ai.provider.invocation import call_api_adapter_stream


class _RecordingCommitter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[PreparedModelRequest] = []
        self.events: list[str] = []

    async def commit_prepared_request(self, request: PreparedModelRequest) -> None:
        self.requests.append(request)
        self.events.append(f"commit:{request.attempt}")
        if self.fail:
            raise RuntimeError("prepared request commit failed")


class _PreparedAdapter:
    api = "faux"

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.transport_calls = 0

    def prepare_request(self, request: ProviderRequest) -> PreparedModelRequest:
        return PreparedModelRequest.from_provider_request(
            request,
            payload={
                "model": request.model.upstream_id or request.model.id,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    async def invoke_prepared_raw(
        self,
        request: ProviderRequest,
        prepared: PreparedModelRequest,
    ) -> AsyncIterator[dict[str, object]]:
        self.transport_calls += 1
        self.events.append(f"transport:{prepared.attempt}")
        assert prepared.payload_for_transport()["model"] == request.model.id
        if prepared.attempt == 1 and request.options is not None:
            retry = request.options.retry
            if retry is not None and retry.max_attempts > 1:
                yield {
                    "type": "response_error",
                    "message": "rate limited",
                    "code": 429,
                    "error_info": {
                        "code": "rate_limit",
                        "message": "rate limited",
                        "source": self.api,
                        "retryable": True,
                        "details": {},
                    },
                }
                return
        yield {"type": "response_start", "response_id": "response-1"}
        yield {"type": "response_done"}

    async def invoke_raw(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[dict[str, object]]:
        raise AssertionError("prepared adapters must use invoke_prepared_raw")
        yield {"type": "response_done"}  # pragma: no cover


class _LegacyAdapter:
    api = "faux"

    async def invoke_raw(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[dict[str, object]]:
        yield {"type": "response_done"}


class _InheritedPreparedAdapter(_PreparedAdapter):
    def __init__(self, events: list[str]) -> None:
        super().__init__(events)
        self.legacy_invoke_calls = 0

    async def invoke_raw(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[dict[str, object]]:
        self.legacy_invoke_calls += 1
        self.events.append("legacy-invoke")
        yield {"type": "response_done"}


def test_prepared_model_request_is_canonical_and_deeply_immutable() -> None:
    prepared = PreparedModelRequest.from_provider_request(
        _request(invocation_id="invocation-1", attempt=2),
        payload={
            "messages": [{"content": "hello", "role": "user"}],
            "model": "faux-model",
        },
    )

    assert prepared.schema_version == 1
    assert prepared.invocation_id == "invocation-1"
    assert prepared.attempt == 2
    assert prepared.canonical_payload == (
        '{"model_visible_headers":{},"payload":{"messages":'
        '[{"content":"hello","role":"user"}],"model":"faux-model"}}'
    )
    assert prepared.payload_hash.startswith("sha256:")
    assert prepared.payload_for_transport() == {
        "messages": [{"content": "hello", "role": "user"}],
        "model": "faux-model",
    }
    with pytest.raises(TypeError):
        prepared.payload["model"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        prepared.payload["messages"][0]["content"] = "changed"  # type: ignore[index]


def test_transport_preserves_adapter_payload_key_order() -> None:
    prepared = PreparedModelRequest.from_provider_request(
        _request(invocation_id="invocation-order"),
        payload={
            "tools": [
                {
                    "name": "lookup",
                    "input_schema": {
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                }
            ],
            "messages": [{"role": "user", "content": "hello"}],
            "model": "faux-model",
        },
    )

    transport = prepared.payload_for_transport()

    assert list(transport) == ["tools", "messages", "model"]
    tools = transport["tools"]
    assert isinstance(tools, list)
    tool = tools[0]
    assert isinstance(tool, dict)
    schema = tool["input_schema"]
    assert isinstance(schema, dict)
    assert list(schema) == ["type", "required", "properties"]


def test_prepared_model_request_rejects_non_json_payload() -> None:
    with pytest.raises(TypeError, match="payload keys must be strings"):
        PreparedModelRequest.from_provider_request(
            _request(invocation_id="invocation-invalid"),
            payload={1: "invalid"},  # type: ignore[dict-item]
        )


@pytest.mark.parametrize(
    ("api", "adapter_type", "payload_field"),
    (
        ("anthropic-messages", AnthropicMessagesAdapter, "messages"),
        ("openai-completions", OpenAIChatCompletionsAdapter, "messages"),
        ("openai-responses", OpenAIResponsesAdapter, "input"),
    ),
)
def test_core_adapter_preparation_freezes_complete_model_visible_payload(
    api: str,
    adapter_type: type[object],
    payload_field: str,
) -> None:
    request = _request(
        api=api,
        headers={"Authorization": "secret-transport-credential"},
        invocation_id="invocation-core",
    )
    adapter = adapter_type()

    assert isinstance(adapter, PreparedRequestAdapter)
    prepared = adapter.prepare_request(request)
    payload = prepared.payload_for_transport()

    assert prepared.invocation_id == "invocation-core"
    assert payload["model"] == "faux-model"
    assert payload_field in payload
    assert "extra_headers" not in payload
    assert "secret-transport-credential" not in prepared.canonical_payload


def test_anthropic_protocol_behavior_headers_are_frozen_before_commit() -> None:
    request = _request(
        api="anthropic-messages",
        invocation_id="invocation-anthropic",
        reasoning_enabled=True,
    )

    prepared = AnthropicMessagesAdapter().prepare_request(request)

    beta_header = prepared.model_visible_headers["anthropic-beta"]
    assert "interleaved-thinking-2025-05-14" in beta_header
    assert beta_header in prepared.canonical_payload


def test_anthropic_transport_header_cannot_enter_frozen_behavior_headers() -> None:
    request = _request(
        api="anthropic-messages",
        headers={"anthropic-beta": "secret-credential-value"},
        invocation_id="invocation-anthropic-secret",
        reasoning_enabled=True,
    )

    prepared = AnthropicMessagesAdapter().prepare_request(request)

    assert "secret-credential-value" not in prepared.canonical_payload
    assert "secret-credential-value" not in prepared.model_visible_headers.values()


def test_prepared_barrier_commits_before_each_retry_transport() -> None:
    async def _run() -> tuple[_PreparedAdapter, _RecordingCommitter]:
        events: list[str] = []
        committer = _RecordingCommitter()
        committer.events = events
        adapter = _PreparedAdapter(events)
        request = _request(
            options=CallOptions(
                retry=RetryOptions(max_attempts=2, max_delay_seconds=0),
                prepared_request_committer=committer,
            )
        )

        stream = await call_api_adapter_stream(adapter, request)
        await stream.result()
        return adapter, committer

    adapter, committer = asyncio.run(_run())

    assert isinstance(adapter, PreparedRequestAdapter)
    assert adapter.transport_calls == 2
    assert committer.events == ["commit:1", "transport:1", "commit:2", "transport:2"]
    assert [request.attempt for request in committer.requests] == [1, 2]
    assert len({request.invocation_id for request in committer.requests}) == 1
    assert len({request.payload_hash for request in committer.requests}) == 1


def test_committer_failure_makes_zero_transport_calls() -> None:
    async def _run() -> tuple[_PreparedAdapter, _RecordingCommitter, Exception]:
        committer = _RecordingCommitter(fail=True)
        adapter = _PreparedAdapter(committer.events)
        request = _request(
            options=CallOptions(prepared_request_committer=committer),
        )
        stream = await call_api_adapter_stream(adapter, request)
        with pytest.raises(AIProviderError) as exc_info:
            await stream.result()
        return adapter, committer, exc_info.value

    adapter, committer, _error = asyncio.run(_run())

    assert committer.events == ["commit:1"]
    assert adapter.transport_calls == 0


def test_swallowed_commit_cancellation_still_makes_zero_transport_calls() -> None:
    class _CancellationSwallowingCommitter:
        async def commit_prepared_request(
            self,
            request: PreparedModelRequest,
        ) -> None:
            del request
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return

    async def _run() -> _PreparedAdapter:
        events: list[str] = []
        adapter = _PreparedAdapter(events)
        request = _request(
            options=CallOptions(
                timeout_seconds=0.01,
                prepared_request_committer=_CancellationSwallowingCommitter(),
            )
        )
        stream = await call_api_adapter_stream(adapter, request)
        with pytest.raises(AIProviderError):
            await stream.result()
        return adapter

    adapter = asyncio.run(_run())

    assert adapter.transport_calls == 0


def test_committer_rejects_adapter_without_prepared_barrier() -> None:
    committer = _RecordingCommitter()

    with pytest.raises(TypeError, match="prepared-request barrier"):
        asyncio.run(
            call_api_adapter_stream(
                _LegacyAdapter(),
                _request(options=CallOptions(prepared_request_committer=committer)),
            )
        )


def test_legacy_adapter_remains_standalone_without_committer() -> None:
    async def _run() -> None:
        stream = await call_api_adapter_stream(_LegacyAdapter(), _request())
        await stream.result()

    asyncio.run(_run())


def test_no_committer_preserves_inherited_invoke_raw_override() -> None:
    async def _run() -> _InheritedPreparedAdapter:
        adapter = _InheritedPreparedAdapter([])
        stream = await call_api_adapter_stream(adapter, _request())
        await stream.result()
        return adapter

    adapter = asyncio.run(_run())

    assert isinstance(adapter, PreparedRequestAdapter)
    assert adapter.legacy_invoke_calls == 1
    assert adapter.transport_calls == 0


def test_provider_runtime_requires_initial_attempt_one() -> None:
    with pytest.raises(ValueError, match="initial attempt must be 1"):
        asyncio.run(call_api_adapter_stream(_LegacyAdapter(), _request(attempt=2)))


def _request(
    *,
    options: CallOptions | None = None,
    invocation_id: str | None = None,
    attempt: int = 1,
    api: str = "faux",
    headers: dict[str, str] | None = None,
    reasoning_enabled: bool | None = None,
) -> ProviderRequest:
    model = Model(
        id="faux-model",
        provider="faux",
        endpoint="faux",
        api=api,
        base_url="https://provider.test/v1",
        auth=Auth(kind="none"),
        capabilities=Capabilities(input=("text",), stream=True),
    )
    return ProviderRequest(
        model=model,
        context=NormalizedContext(system_prompt=None),
        options=options,
        base_url="https://provider.test/v1",
        headers=headers or {},
        reasoning_enabled=reasoning_enabled,
        invocation_id=invocation_id,
        attempt=attempt,
    )
