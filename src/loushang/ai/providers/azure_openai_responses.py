from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from loushang.ai.model.domain import EndpointProtocolFeatures, EndpointWireDialect
from loushang.ai.options import get_reasoning_summary
from loushang.ai.output_budget import resolve_output_token_budget
from loushang.ai.provider import resolve_provider_request
from loushang.ai.providers.openai_responses_shared import (
    convert_responses_messages,
    convert_responses_tools,
    process_responses_stream,
)
from loushang.ai.providers.provider_helpers import (
    close_provider_stream,
    extract_sdk_api_key,
)
from loushang.ai.structured import openai_responses_text_format

DEFAULT_AZURE_API_VERSION = "v1"


class AzureOpenAIResponsesProvider:
    api = "azure-openai-responses"

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def _stream_raw_parts(
        self, model, context, options, request=None
    ) -> AsyncIterator[dict]:
        return self.stream_raw(model, context, options, request)

    async def stream_raw(
        self, model, context, options, request=None
    ) -> AsyncIterator[dict]:
        resolved = resolve_provider_request(
            self.api,
            model,
            options=options,
            request=request,
        )
        normalized = context
        protocol = _request_protocol(resolved)
        dialect = _request_dialect(resolved)

        try:
            from openai import AsyncAzureOpenAI  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "openai SDK is not installed. Install via `pip install openai`"
            ) from e

        api_key = extract_sdk_api_key(
            resolved.headers or {},
            error_message=(
                "Azure OpenAI Responses provider requires an API key "
                "(Authorization: Bearer or x-api-key)"
            ),
        )
        azure_endpoint = _resolve_azure_endpoint(resolved.base_url, options)
        api_version = _resolve_api_version(options)
        deployment_name = _resolve_deployment_name(
            model,
            getattr(resolved, "upstream_model_id", None),
            options,
        )
        client = self._client or AsyncAzureOpenAI(  # type: ignore[call-arg]
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )

        params: dict[str, Any] = {
            "model": deployment_name,
            "input": convert_responses_messages(
                model,
                normalized,
                protocol,
                dialect,
                getattr(resolved, "capabilities", None),
            ),
            "stream": True,
            "store": False,
            "max_output_tokens": resolve_output_token_budget(
                model,
                resolved,
            ).value,
        }
        mapped_tools = convert_responses_tools(normalized.get("tools"))
        if isinstance(mapped_tools, list) and mapped_tools:
            params["tools"] = mapped_tools
            params["tool_choice"] = getattr(options, "tool_choice", None) or "auto"
        reasoning_effort = getattr(resolved, "reasoning_effort", None)
        if reasoning_effort:
            params["reasoning"] = {"effort": reasoning_effort}
        reasoning_summary = get_reasoning_summary(options)
        if reasoning_summary:
            params.setdefault("reasoning", {})["summary"] = reasoning_summary
        if getattr(options, "temperature", None) is not None:
            params["temperature"] = getattr(options, "temperature")
        text_format = openai_responses_text_format(options)
        if text_format is not None:
            params["text"] = text_format

        sdk_stream = await client.responses.create(**params)
        try:
            async for part in process_responses_stream(sdk_stream, options=options):
                yield part
        finally:
            await close_provider_stream(sdk_stream)


def _request_protocol(request: object) -> EndpointProtocolFeatures:
    protocol = getattr(request, "adapter_protocol", None)
    if isinstance(protocol, EndpointProtocolFeatures):
        return protocol
    return EndpointProtocolFeatures()


def _request_dialect(request: object) -> EndpointWireDialect:
    dialect = getattr(request, "adapter_dialect", None)
    if isinstance(dialect, EndpointWireDialect):
        return dialect
    return EndpointWireDialect()


def _resolve_azure_endpoint(base_url: str | None, options: object | None) -> str:
    value = (
        getattr(options, "azure_base_url", None) if options is not None else None
    ) or os.getenv("AZURE_OPENAI_BASE_URL")
    if not isinstance(value, str) or not value:
        value = base_url
    if not isinstance(value, str) or not value:
        raise ValueError(
            "Azure OpenAI base URL is required. Set AZURE_OPENAI_BASE_URL "
            "or define baseUrl/baseUrlEnv in the model endpoint."
        )
    return value.rstrip("/")


def _resolve_api_version(options: object | None) -> str:
    value = (
        getattr(options, "azure_api_version", None) if options is not None else None
    ) or os.getenv("AZURE_OPENAI_API_VERSION")
    return value if isinstance(value, str) and value else DEFAULT_AZURE_API_VERSION


def _resolve_deployment_name(
    model,
    upstream_model_id: str | None,
    options: object | None,
) -> str:
    explicit = (
        getattr(options, "azure_deployment_name", None) if options is not None else None
    )
    if isinstance(explicit, str) and explicit:
        return explicit
    mapping = _parse_deployment_map(os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_MAP"))
    if model.id in mapping:
        return mapping[model.id]
    if upstream_model_id and upstream_model_id in mapping:
        return mapping[upstream_model_id]
    return upstream_model_id or model.id


def _parse_deployment_map(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    result: dict[str, str] = {}
    for entry in value.split(","):
        key, sep, deployment = entry.partition("=")
        if not sep:
            continue
        key = key.strip()
        deployment = deployment.strip()
        if key and deployment:
            result[key] = deployment
    return result
