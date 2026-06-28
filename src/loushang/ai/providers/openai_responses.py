from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from loushang.ai.errors import UnsupportedCapabilityError
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.model.domain import OpenAIResponsesConfig
from loushang.ai.options import (
    get_reasoning_effort,
    get_reasoning_summary,
)
from loushang.ai.output_budget import resolve_output_token_budget
from loushang.ai.provider import ProviderRequest
from loushang.ai.provider.errors import provider_error_part
from loushang.ai.providers.openai_responses_shared import (
    build_copilot_dynamic_headers,
    convert_responses_messages,
    convert_responses_tools,
    process_responses_response,
    process_responses_stream,
)
from loushang.ai.providers.provider_helpers import (
    apply_session_headers,
    close_provider_stream,
    extract_sdk_api_key,
    sdk_default_headers,
)
from loushang.ai.structured import openai_responses_text_format
from loushang.ai.trace import emit_trace as _emit_trace


def _resolve_cache_retention(options: object | None) -> str | None:
    cache_retention = (
        getattr(options, "cache_retention", None) if options is not None else None
    )
    if isinstance(cache_retention, str):
        return cache_retention
    if (os.getenv("PI_CACHE_RETENTION") or "").lower() == "long":
        return "long"
    return None


def _apply_prompt_cache_params(
    params: dict[str, Any],
    *,
    adapter_config: OpenAIResponsesConfig,
    cache_retention: str | None,
    session_id: str | None,
) -> None:
    if (cache_retention or "short") == "none":
        return
    if adapter_config.prompt_cache_key and isinstance(session_id, str) and session_id:
        params["prompt_cache_key"] = session_id
    if cache_retention == "long" and adapter_config.long_cache_retention:
        params["prompt_cache_retention"] = "24h"


def _validate_cache_session_options(
    model: object,
    resolved: object,
    *,
    adapter_config: OpenAIResponsesConfig,
    cache_retention: str | None,
    session_id: str | None,
) -> None:
    if cache_retention == "long" and not adapter_config.long_cache_retention:
        raise UnsupportedCapabilityError(
            f"Model {getattr(model, 'id', '<unknown>')!r} does not support long cache retention",
            source=getattr(resolved, "api", None),
            provider=getattr(resolved, "provider", None),
            endpoint=getattr(resolved, "endpoint", None),
            model=getattr(model, "id", None),
            details={"capability": "cache_long_retention"},
        )


class OpenAIResponsesProvider:
    api = "openai-responses"
    supports_structured_output = True

    def __init__(
        self, *, client: Any | None = None, base_url: str | None = None
    ) -> None:
        self._client = client
        self._base_url = base_url

    async def invoke_raw(self, request: ProviderRequest) -> AsyncIterator[RawPart]:
        model = request.model
        options = request.options
        resolved = request

        def _debug(event: str, data: dict | None = None) -> None:
            # Allow callers to suppress provider SDK trace events explicitly.
            if options is not None:
                with suppress(Exception):
                    if (
                        getattr(options, "debug", None) is False
                        or getattr(options, "quiet_debug", None) is True
                    ):
                        return
            _emit_trace(options, {"type": f"sdk:{event}", **(data or {})})

        normalized = request.context
        adapter_config = _request_adapter_config(resolved)

        # 延迟导入 OpenAI SDK
        try:
            from openai import AsyncOpenAI  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "openai SDK is not installed. Install via `pip install openai`"
            ) from e

        headers = resolved.headers or {}
        api_key = extract_sdk_api_key(
            headers,
            error_message=(
                "OpenAI SDK provider requires an API key "
                "(Authorization: Bearer or x-api-key)"
            ),
        )

        default_headers = sdk_default_headers(headers)
        if _uses_copilot_dynamic_headers(resolved):
            default_headers.update(
                build_copilot_dynamic_headers(list(normalized.messages))
            )

        # 优先使用 provider 的 base_url（如果提供），否则使用 resolved 的 base_url
        effective_base_url = (
            self._base_url if self._base_url is not None else resolved.base_url
        )

        # 构造 Responses API 输入。下一步会继续向 pi-ai 的 shared conversion 收敛。
        capabilities = getattr(resolved, "capabilities", None)
        input_items = convert_responses_messages(
            model,
            normalized,
            adapter_config,
            capabilities,
        )

        cache_retention = _resolve_cache_retention(options)
        session_id = (
            getattr(options, "session_id", None) if options is not None else None
        )
        _validate_cache_session_options(
            model,
            resolved,
            adapter_config=adapter_config,
            cache_retention=cache_retention,
            session_id=session_id,
        )
        should_apply_session_headers = (
            (cache_retention or "short") != "none"
            and isinstance(session_id, str)
            and session_id
            and (
                adapter_config.session_id_header
                or adapter_config.session_affinity_headers
            )
        )
        if should_apply_session_headers:
            apply_session_headers(
                default_headers,
                session_id,
                include_session_id=adapter_config.session_id_header,
                include_client_request_id=(
                    adapter_config.session_id_header
                    or adapter_config.session_affinity_headers
                ),
                include_affinity=adapter_config.session_affinity_headers,
            )

        client = self._client or AsyncOpenAI(  # type: ignore[call-arg]
            api_key=api_key,
            base_url=effective_base_url,
            default_headers=default_headers or None,
        )
        _debug("client", {"base_url": effective_base_url, "headers": default_headers})

        upstream_model_id = getattr(resolved, "upstream_model_id", None) or model.id
        is_stream_request = getattr(resolved, "mode", "stream") == "stream"
        params: dict[str, Any] = {
            "model": upstream_model_id,
            "input": input_items,
            "store": False,
        }
        if is_stream_request:
            params["stream"] = True
        # tools（如果提供）映射到 Responses API，触发结构化 function_call 事件
        mapped_tools = convert_responses_tools(normalized.tools)
        if isinstance(mapped_tools, list) and mapped_tools:
            params["tools"] = mapped_tools
            # 缺省让服务端自动选择是否调用工具（仅当 tools 非空）
            explicit_tool_choice = (
                getattr(options, "tool_choice", None) if options is not None else None
            )
            if explicit_tool_choice in {"auto", "none", "required"}:
                params["tool_choice"] = explicit_tool_choice
            elif "tool_choice" not in params:
                params["tool_choice"] = "auto"
        _apply_prompt_cache_params(
            params,
            adapter_config=adapter_config,
            cache_retention=cache_retention,
            session_id=session_id,
        )
        params["max_output_tokens"] = resolve_output_token_budget(
            model,
            resolved,
        ).value
        # 温度
        if getattr(options, "temperature", None) is not None:
            params["temperature"] = getattr(options, "temperature")
        # 推理配置（最小实现）
        if _supports_reasoning(capabilities):
            reasoning_effort = get_reasoning_effort(options) or getattr(
                resolved, "reasoning_effort", None
            )
            reasoning_summary = get_reasoning_summary(options)
            if reasoning_effort or reasoning_summary:
                params["reasoning"] = {
                    "effort": reasoning_effort or "medium",
                    "summary": reasoning_summary or "auto",
                }
                params["include"] = ["reasoning.encrypted_content"]
            else:
                params["reasoning"] = {"effort": "none"}
        text_format = openai_responses_text_format(options)
        if text_format is not None:
            params["text"] = text_format

        _debug("payload", {"params": {k: v for k, v in params.items() if k != "input"}})

        # 发送请求
        try:
            response = await client.responses.create(**params)
        except Exception as e:
            _debug("stream_error", {"message": str(e)})
            yield provider_error_part(e, source=self.api)
            return
        if not is_stream_request:
            for part in process_responses_response(
                response,
                options=options,
                source=self.api,
            ):
                yield part
            return

        try:
            async for part in process_responses_stream(
                response,
                options=options,
                source=self.api,
            ):
                yield part
        except Exception as e:
            _debug("stream_iter_error", {"message": str(e)})
            yield provider_error_part(e, source=self.api)
        finally:
            await close_provider_stream(response)


def _supports_reasoning(capabilities: object | None) -> bool:
    if capabilities is None:
        return False
    supports_thinking = getattr(capabilities, "supports_thinking", None)
    if supports_thinking is not None:
        return bool(supports_thinking)
    return bool(getattr(capabilities, "reasoning", False))


def _request_adapter_config(request: object) -> OpenAIResponsesConfig:
    adapter_config = getattr(request, "adapter_config", None)
    if isinstance(adapter_config, OpenAIResponsesConfig):
        return adapter_config
    return OpenAIResponsesConfig()


def _uses_copilot_dynamic_headers(resolved: object) -> bool:
    transport = getattr(resolved, "transport", None)
    return getattr(transport, "kind", None) == "github-copilot"
