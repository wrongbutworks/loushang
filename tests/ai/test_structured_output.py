from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from loushang.ai import (
    CallOptions,
    StructuredOutputError,
    StructuredOutputOptions,
    complete_structured,
)
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.errors import UnsupportedCapabilityError
from loushang.ai.model import Capabilities, Endpoint, Model, ModelRegistry, Provider
from loushang.ai.provider import ProviderRequest
from loushang.ai.structured import (
    openai_chat_response_format,
    openai_responses_text_format,
    parse_structured_output,
)
from loushang.ai.types import AssistantMessage, TextPart, Usage


def _assistant_json(text: str) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text=text)],
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
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )


@dataclass(frozen=True)
class _AnswerModel:
    answer: str
    score: int

    @classmethod
    def model_json_schema(cls):
        return {
            "title": "AnswerModel",
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "score": {"type": "integer"},
            },
            "required": ["answer", "score"],
            "additionalProperties": False,
        }

    @classmethod
    def model_validate(cls, value):
        if not isinstance(value, dict):
            raise TypeError("expected object")
        return cls(answer=str(value["answer"]), score=int(value["score"]))


def test_structured_output_formats_openai_payloads_from_schema_type() -> None:
    options = CallOptions(
        output=StructuredOutputOptions(mode="json_schema", schema=_AnswerModel)
    )

    assert openai_chat_response_format(options) == {
        "type": "json_schema",
        "json_schema": {
            "name": "AnswerModel",
            "schema": _AnswerModel.model_json_schema(),
            "strict": True,
        },
    }
    assert openai_responses_text_format(options) == {
        "format": {
            "type": "json_schema",
            "name": "AnswerModel",
            "schema": _AnswerModel.model_json_schema(),
            "strict": True,
        }
    }


def test_structured_output_json_object_parses_raw_message() -> None:
    output = StructuredOutputOptions(mode="json_object")

    result = parse_structured_output(_assistant_json('{"answer":"ok"}'), output)

    assert result.raw.model == "gpt-test"
    assert result.parsed == {"answer": "ok"}
    assert openai_chat_response_format(CallOptions(output=output)) == {
        "type": "json_object"
    }


def test_structured_output_schema_type_parses_pydantic_like_object() -> None:
    output = StructuredOutputOptions(mode="json_schema", schema=_AnswerModel)

    result = parse_structured_output(
        _assistant_json('{"answer":"ok","score":7}'),
        output,
    )

    assert result.parsed == _AnswerModel(answer="ok", score=7)


def test_structured_output_reports_parse_errors() -> None:
    output = StructuredOutputOptions(mode="json_schema", schema=_AnswerModel)

    with pytest.raises(StructuredOutputError) as exc_info:
        parse_structured_output(_assistant_json("not json"), output)

    assert "not valid JSON" in str(exc_info.value)
    assert exc_info.value.info.details["reason"] == "Expecting value"


def test_complete_structured_returns_raw_and_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _StructuredProvider()
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    _patch_resolved_request(monkeypatch, api="openai-responses")

    result = asyncio.run(
        complete_structured(
            _Model(),
            {"messages": []},
            StructuredOutputOptions(mode="json_object"),
            options=CallOptions(),
            provider_registry=registry,
        )
    )

    assert result.raw.response_id == "structured-demo"
    assert result.parsed == {"answer": "ok"}
    assert isinstance(provider.options.output, StructuredOutputOptions)


def test_complete_structured_uses_provider_declared_mapping_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _StructuredProvider(api="custom-structured")
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    _patch_resolved_request(monkeypatch, api="custom-structured")

    result = asyncio.run(
        complete_structured(
            _Model(),
            {"messages": []},
            StructuredOutputOptions(mode="json_object"),
            options=CallOptions(),
            provider_registry=registry,
        )
    )

    assert result.raw.response_id == "structured-demo"
    assert result.parsed == {"answer": "ok"}


def test_complete_structured_rejects_provider_without_mapping_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _StructuredProvider(api="openai-responses", supports_mapping=False)
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    _patch_resolved_request(monkeypatch, api="openai-responses")

    with pytest.raises(
        UnsupportedCapabilityError,
        match="does not support structured output mapping",
    ):
        asyncio.run(
            complete_structured(
                _Model(),
                {"messages": []},
                StructuredOutputOptions(mode="json_object"),
                options=CallOptions(),
                provider_registry=registry,
            )
        )


@dataclass
class _Model:
    id: str = "gpt-test"


class _StructuredProvider:
    def __init__(
        self, api: str = "openai-responses", *, supports_mapping: bool = True
    ) -> None:
        self.api = api
        self.supports_structured_output = supports_mapping
        self.options = None

    async def invoke_raw(self, request):
        self.options = request.options
        yield {"type": "response_start", "response_id": "structured-demo"}
        yield {"type": "text_delta", "text": '{"answer":"ok"}'}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


def _patch_resolved_request(monkeypatch: pytest.MonkeyPatch, *, api: str) -> None:
    def _resolve_request(_model, options=None):
        del options
        endpoint = Endpoint(
            id=api,
            provider="test-provider",
            api=api,
            base_url="https://provider.test/v1",
            models={
                _model.id: Model(
                    id=_model.id,
                    provider="test-provider",
                    endpoint=api,
                    capabilities=Capabilities(
                        input=("text",),
                        stream=True,
                        structured_output=True,
                    ),
                )
            },
        )
        request_model = ModelRegistry.from_providers(
            {
                "test-provider": Provider(
                    id="test-provider",
                    endpoints={api: endpoint},
                )
            }
        ).get_model("test-provider", api, _model.id)
        return ProviderRequest(
            api=api,
            provider="test-provider",
            endpoint=api,
            base_url="https://provider.test/v1",
            model=request_model,
            capabilities=request_model.capabilities,
        )

    monkeypatch.setattr(
        "loushang.ai.api.streaming.resolve_request_for_model",
        _resolve_request,
    )
