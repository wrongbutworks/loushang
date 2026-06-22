from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from loushang.ai import (
    CallOptions,
    StructuredOutputError,
    StructuredOutputOptions,
    complete_structured,
)
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.model import Capabilities
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
            registry=registry,
        )
    )

    assert result.raw.response_id == "structured-demo"
    assert result.parsed == {"answer": "ok"}
    assert isinstance(provider.options.output, StructuredOutputOptions)


def test_complete_structured_rejects_unmapped_provider_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _StructuredProvider(api="anthropic-messages")
    registry = ApiProviderRegistry()
    registry.register_api_provider(provider)
    _patch_resolved_request(monkeypatch, api="anthropic-messages")

    with pytest.raises(ValueError, match="does not support structured output mapping"):
        asyncio.run(
            complete_structured(
                _Model(),
                {"messages": []},
                StructuredOutputOptions(mode="json_object"),
                options=CallOptions(),
                registry=registry,
            )
        )


@dataclass
class _Model:
    id: str = "gpt-test"


class _StructuredProvider:
    def __init__(self, api: str = "openai-responses") -> None:
        self.api = api
        self.options = None

    async def stream_raw(self, model, context, options, request):
        del model, context, request
        self.options = options
        yield {"type": "response_start", "response_id": "structured-demo"}
        yield {"type": "text_delta", "text": '{"answer":"ok"}'}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


def _patch_resolved_request(monkeypatch: pytest.MonkeyPatch, *, api: str) -> None:
    def _resolve_request(_model, options=None):
        del options
        return SimpleNamespace(
            api=api,
            provider="test-provider",
            capabilities=Capabilities(
                input=("text",),
                stream=True,
                structured_output=True,
            ),
        )

    def _resolve_provider_request(provider_api, _model, *, options=None, request=None):
        del options
        resolved = request if request is not None else _resolve_request(_model)
        if resolved.api != provider_api:
            raise ValueError(
                f"Mismatched api: provider={provider_api!r} request.api={resolved.api!r}"
            )
        return resolved

    monkeypatch.setattr(
        "loushang.ai.api.streaming.resolve_request_for_model",
        _resolve_request,
    )
    monkeypatch.setattr(
        "loushang.ai.provider.invocation.resolve_provider_request",
        _resolve_provider_request,
    )
