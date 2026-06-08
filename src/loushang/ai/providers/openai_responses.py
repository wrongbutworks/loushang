from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

from loushang.ai.context import ensure_normalized_context
from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.model.compat_schema import (
    SEND_SESSION_ID_HEADER,
    SUPPORTS_LONG_CACHE_RETENTION,
    UPSTREAM_MODEL_ID,
    compat_bool,
    compat_str,
)
from loushang.ai.options import PairingMode
from loushang.ai.output_budget import resolve_output_token_budget
from loushang.ai.provider import resolve_request_for_model
from loushang.ai.provider.cancellation import is_signal_cancelled
from loushang.ai.provider.errors import provider_error_part
from loushang.ai.providers.openai_responses_shared import (
    build_copilot_dynamic_headers,
    convert_responses_messages,
    convert_responses_tools,
    process_responses_stream,
)
from loushang.ai.providers.provider_helpers import (
    apply_session_headers,
    extract_sdk_api_key,
    sdk_default_headers,
)
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
    compat: dict[str, object],
    cache_retention: str | None,
    session_id: str | None,
) -> None:
    if (cache_retention or "short") == "none":
        return
    if isinstance(session_id, str) and session_id:
        params["prompt_cache_key"] = session_id
    if cache_retention == "long" and compat_bool(compat, SUPPORTS_LONG_CACHE_RETENTION):
        params["prompt_cache_retention"] = "24h"


class OpenAIResponsesProvider:
    api = "openai-responses"

    def __init__(
        self, *, client: Any | None = None, base_url: str | None = None
    ) -> None:
        self._client = client
        self._base_url = base_url

    async def stream(self, model, context, options):
        resolved = resolve_request_for_model(model, options=options)
        stream = AssistantMessageEventStream()
        assembler = RawAssembler(
            stream=stream,
            api=resolved.api,
            provider=model.provider_id,
            model=model.id,
            pricing=getattr(model, "pricing", None),
        )

        async def _run() -> None:
            signal = getattr(options, "signal", None) if options is not None else None
            if is_signal_cancelled(signal):
                assembler.feed({"type": "aborted"})
                return
            try:
                async for part in self._stream_raw_parts(model, context, options):
                    if is_signal_cancelled(signal):
                        assembler.feed({"type": "aborted"})
                        return
                    assembler.feed(part)
            except Exception as error:
                assembler.feed(provider_error_part(error, source=self.api))

        stream.attach_task(asyncio.create_task(_run()))
        return stream

    async def stream_simple(self, model, context, options):
        return await self.stream(model, context, options)

    async def _stream_raw_parts(self, model, context, options) -> AsyncIterator[dict]:
        def _pairing_mode() -> PairingMode:
            if options is None:
                return "repair"
            pairing_mode = getattr(options, "pairing_mode", "repair")
            if pairing_mode == "strict":
                return "strict"
            return "repair"

        def _debug(event: str, data: dict | None = None) -> None:
            # Allow callers to suppress provider SDK trace events explicitly.
            if options is not None:
                try:
                    if (
                        getattr(options, "debug", None) is False
                        or getattr(options, "quiet_debug", None) is True
                    ):
                        return
                except Exception:
                    pass
            _emit_trace(options, {"type": f"sdk:{event}", **(data or {})})

        normalized = ensure_normalized_context(
            context,
            model=model,
            pairing_mode=_pairing_mode(),
        )
        resolved = resolve_request_for_model(model, options=options)
        compat = dict(getattr(resolved, "compat", {}) or {})

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
        if getattr(model, "provider_id", "") == "github-copilot":
            default_headers.update(
                build_copilot_dynamic_headers(normalized.get("messages", []))
            )

        # 优先使用 provider 的 base_url（如果提供），否则使用 resolved 的 base_url
        effective_base_url = (
            self._base_url if self._base_url is not None else resolved.base_url
        )

        # 构造 Responses API 输入。下一步会继续向 pi-ai 的 shared conversion 收敛。
        input_items = convert_responses_messages(model, normalized, compat)

        cache_retention = _resolve_cache_retention(options)
        session_id = (
            getattr(options, "session_id", None) if options is not None else None
        )
        if (
            (cache_retention or "short") != "none"
            and isinstance(session_id, str)
            and session_id
        ):
            apply_session_headers(
                default_headers,
                session_id,
                include_session_id=compat_bool(
                    compat, SEND_SESSION_ID_HEADER, default=True
                ),
            )

        client = self._client or AsyncOpenAI(  # type: ignore[call-arg]
            api_key=api_key,
            base_url=effective_base_url,
            default_headers=default_headers or None,
        )
        _debug("client", {"base_url": effective_base_url, "headers": default_headers})

        upstream_model_id = compat_str(compat, UPSTREAM_MODEL_ID) or model.id
        params: dict[str, Any] = {
            "model": upstream_model_id,
            "input": input_items,
            "stream": True,
            "store": False,
        }
        # tools（如果提供）映射到 Responses API，触发结构化 function_call 事件
        tools_src: list[Any] = []
        n_tools = normalized.get("tools")
        if isinstance(n_tools, list):
            tools_src = n_tools
        mapped_tools = convert_responses_tools(tools_src)
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
            compat=compat,
            cache_retention=cache_retention,
            session_id=session_id,
        )
        params["max_output_tokens"] = resolve_output_token_budget(
            model,
            resolved,
            options,
        ).value
        # 温度
        if getattr(options, "temperature", None) is not None:
            params["temperature"] = getattr(options, "temperature")
        # service_tier（可选）
        if getattr(options, "service_tier", None) is not None:
            params["service_tier"] = getattr(options, "service_tier")
        # 推理配置（最小实现）
        if getattr(model, "reasoning", False):
            reasoning_effort = (
                getattr(options, "reasoning_effort", None)
                or getattr(options, "reasoningEffort", None)
                or getattr(options, "reasoning", None)
                or getattr(resolved, "reasoning_effort", None)
            )
            reasoning_summary = getattr(options, "reasoning_summary", None) or getattr(
                options, "reasoningSummary", None
            )
            if reasoning_effort or reasoning_summary:
                params["reasoning"] = {
                    "effort": reasoning_effort or "medium",
                    "summary": reasoning_summary or "auto",
                }
                params["include"] = ["reasoning.encrypted_content"]
            else:
                params["reasoning"] = {"effort": "none"}

        # options.on_payload：允许调用方观察/修改最终请求参数（对齐 pi-ai 语义）
        try:
            cb = getattr(options, "on_payload", None) if options is not None else None
            if callable(cb):
                next_params = cb(params, model)
                if asyncio.iscoroutine(next_params):
                    next_params = await next_params
                if isinstance(next_params, dict):
                    params = next_params
        except Exception as e:
            # on_payload 是观察/调试钩子，失败不应影响主流程，但要可诊断。
            _debug("on_payload_error", {"message": str(e)})
        _debug("payload", {"params": {k: v for k, v in params.items() if k != "input"}})

        # 发送请求
        try:
            stream_ctx = await client.responses.create(**params)
        except Exception as e:
            _debug("stream_error", {"message": str(e)})
            yield provider_error_part(e, source=self.api)
            return
        await _notify_provider_response(options, stream_ctx, model)

        try:
            async for part in process_responses_stream(stream_ctx, options=options):
                yield part
        except Exception as e:
            _debug("stream_iter_error", {"message": str(e)})
            yield provider_error_part(e, source=self.api)


async def _notify_provider_response(options, response, model) -> None:
    callback = getattr(options, "on_response", None) if options is not None else None
    if not callable(callback):
        return
    try:
        result = callback(response, model)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        pass
