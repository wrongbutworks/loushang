from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.model.domain import (
    EndpointProtocolFeatures,
    EndpointWireDialect,
    SupportStatus,
)
from loushang.ai.options import get_timeout_seconds
from loushang.ai.output_budget import resolve_output_token_budget
from loushang.ai.provider import resolve_provider_request
from loushang.ai.provider.cancellation import is_signal_cancelled
from loushang.ai.provider.errors import provider_error_part
from loushang.ai.providers.openai_responses_shared import build_copilot_dynamic_headers
from loushang.ai.providers.provider_helpers import (
    apply_session_headers,
    extract_sdk_api_key,
    sdk_default_headers,
)
from loushang.ai.tool.providers import sanitize_tool_parameters
from loushang.ai.tool.transform import (
    MISSING_TOOL_RESULT_TEXT,
    TOOL_RESULTS_PROCESSED_ASSISTANT_TEXT,
)
from loushang.ai.trace import emit_trace as _emit_trace
from loushang.ai.types import AssistantMessage, TextPart, Tool, ToolResultMessage
from loushang.ai.utils import sanitize_surrogates


class OpenAICompletionsProvider:
    api = "openai-completions"

    def __init__(
        self, *, client: Any | None = None, base_url: str | None = None
    ) -> None:
        self._client = client
        self._base_url = base_url

    async def stream(self, model, context, options, request=None):
        resolved = resolve_provider_request(
            self.api,
            model,
            options=options,
            request=request,
        )
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
                async for part in self._stream_raw_parts(
                    model, context, options, resolved
                ):
                    if is_signal_cancelled(signal):
                        assembler.feed({"type": "aborted"})
                        return
                    assembler.feed(part)
            except Exception as error:
                assembler.feed(provider_error_part(error, source=self.api))

        stream.attach_task(asyncio.create_task(_run()))
        return stream

    async def _stream_raw_parts(
        self, model, context, options, request=None
    ) -> AsyncIterator[dict]:
        def _debug(event: str, data: dict | None = None) -> None:
            _emit_trace(options, {"type": f"sdk:{event}", **(data or {})})

        resolved = resolve_provider_request(
            self.api,
            model,
            options=options,
            request=request,
        )
        normalized = context
        protocol = _request_protocol(resolved)
        dialect = _request_dialect(resolved)
        supports_usage_in_streaming = _is_supported(protocol.streaming.usage)
        supports_store = _is_supported(protocol.store)
        max_tokens_field = dialect.max_output_tokens_field or "max_tokens"
        thinking_format = dialect.reasoning.wire_format
        reasoning_effort_map = dict(protocol.reasoning.effort_map)
        supports_reasoning_effort = _is_supported(protocol.reasoning.effort)

        # OpenAI Python SDK
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
            copilot_headers = build_copilot_dynamic_headers(
                normalized.get("messages", [])
            )
            default_headers.update(copilot_headers)
        cache_retention = (
            getattr(options, "cache_retention", None) if options is not None else None
        ) or "short"
        session_id = (
            getattr(options, "session_id", None) if options is not None else None
        )
        if (
            cache_retention != "none"
            and isinstance(session_id, str)
            and session_id
            and _is_supported(protocol.session.affinity_headers)
        ):
            apply_session_headers(
                default_headers,
                session_id,
                include_affinity=True,
            )

        timeout_s = _resolve_timeout_seconds(options, resolved)
        # 优先使用 provider 的 base_url（如果提供），否则使用 resolved 的 base_url
        effective_base_url = (
            self._base_url if self._base_url is not None else resolved.base_url
        )
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": effective_base_url,
            "default_headers": default_headers or None,
        }
        if isinstance(timeout_s, int | float):
            client_kwargs["timeout"] = timeout_s
        client = self._client or AsyncOpenAI(**client_kwargs)  # type: ignore[call-arg]
        _debug("client", {"base_url": effective_base_url, "headers": default_headers})

        capabilities = getattr(resolved, "capabilities", None)
        messages_param = _build_messages(
            model,
            normalized,
            protocol,
            dialect,
            capabilities,
        )
        tools_param = _build_tools(normalized.get("tools"), protocol)
        if tools_param is None and _has_tool_history(normalized.get("messages", [])):
            tools_param = []
        cache_control = _get_cache_control(protocol, dialect, cache_retention)
        if cache_control is not None:
            _apply_anthropic_cache_control(messages_param, tools_param, cache_control)

        max_tokens = resolve_output_token_budget(model, resolved).value
        upstream_model_id = getattr(resolved, "upstream_model_id", None) or model.id
        params: dict[str, Any] = {
            "model": upstream_model_id,
            "messages": messages_param,
            "stream": True,
        }
        _apply_prompt_cache_params(
            params,
            protocol=protocol,
            cache_retention=cache_retention,
            session_id=session_id,
        )
        extra_body: dict[str, Any] = {}
        if supports_usage_in_streaming:
            params["stream_options"] = {"include_usage": True}
        if supports_store:
            params["store"] = False
        if max_tokens_field == "max_tokens":
            params["max_tokens"] = max_tokens
        else:
            params["max_completion_tokens"] = max_tokens
        if getattr(options, "temperature", None) is not None:
            params["temperature"] = getattr(options, "temperature")
        if tools_param is not None:
            params["tools"] = tools_param
            if dialect.tools.stream_flag:
                params["tool_stream"] = True
        tool_choice = getattr(options, "tool_choice", None)
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        reasoning_effort = getattr(resolved, "reasoning_effort", None)
        _apply_reasoning_params(
            params,
            extra_body,
            model=model,
            thinking_format=thinking_format,
            reasoning_effort=reasoning_effort,
            reasoning_effort_map=reasoning_effort_map,
            supports_reasoning_effort=supports_reasoning_effort,
            capabilities=capabilities,
        )
        _apply_provider_routing(
            params,
            provider_id=resolved.provider,
            base_url=effective_base_url,
            request_overrides=getattr(
                getattr(resolved, "routing", None),
                "request_overrides",
                {},
            ),
        )
        if extra_body:
            params["extra_body"] = extra_body
        _debug(
            "payload", {"params": {k: v for k, v in params.items() if k != "messages"}}
        )

        try:
            stream_ctx = await client.chat.completions.create(**params)
        except Exception as e:
            _debug("stream_error", {"message": str(e)})
            yield provider_error_part(e, source=self.api)
            return
        await _notify_provider_response(options, stream_ctx, model)
        # 流式超时/空闲看门狗：若超过 timeout 无增量则报错退出，避免“假死”
        inactivity_timeout = (
            timeout_s if isinstance(timeout_s, (int, float)) and timeout_s > 0 else 30
        )
        _debug("stream_begin", {"inactivity_timeout": inactivity_timeout})
        try:
            emitted_response_start = False
            emitted_any_text = False
            active_tool_call_id: str | None = None
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        stream_ctx.__anext__(), timeout=inactivity_timeout
                    )  # type: ignore[attr-defined]
                except StopAsyncIteration:
                    _debug("stream_end", {"reason": "upstream_eof"})
                    break
                except asyncio.TimeoutError:
                    _debug("stream_timeout", {"after_seconds": inactivity_timeout})
                    yield {
                        "type": "response_error",
                        "message": f"inactivity timeout after {inactivity_timeout}s",
                    }
                    yield {"type": "response_done"}
                    break
                except Exception as e:
                    _debug("stream_iter_error", {"message": str(e)})
                    yield provider_error_part(e, source=self.api)
                    yield {"type": "response_done"}
                    break
                if not chunk or not hasattr(chunk, "choices"):
                    continue
                choice = chunk.choices[0] if chunk.choices else None
                if choice is None:
                    continue
                # response id
                if not emitted_response_start:
                    emitted_response_start = True
                    resp_id = getattr(chunk, "id", None)
                    _debug("event", {"kind": "response_start", "response_id": resp_id})
                    yield {
                        "type": "response_start",
                        **({"response_id": resp_id} if resp_id else {}),
                    }
                # usage
                usage = getattr(chunk, "usage", None)
                if usage is None and hasattr(choice, "usage"):
                    usage = getattr(choice, "usage")
                if usage is not None:
                    _input = getattr(usage, "prompt_tokens", 0) - (
                        getattr(
                            getattr(usage, "prompt_tokens_details", None) or {},
                            "cached_tokens",
                            0,
                        )
                        or 0
                    )
                    _output = (getattr(usage, "completion_tokens", 0) or 0) + (
                        getattr(
                            getattr(usage, "completion_tokens_details", None) or {},
                            "reasoning_tokens",
                            0,
                        )
                        or 0
                    )
                    _cache_read = (
                        getattr(
                            getattr(usage, "prompt_tokens_details", None) or {},
                            "cached_tokens",
                            0,
                        )
                        or 0
                    )
                    _total = (_input or 0) + (_output or 0) + (_cache_read or 0)
                    _debug(
                        "event",
                        {
                            "kind": "usage_delta",
                            "input": _input,
                            "output": _output,
                            "cache_read": _cache_read,
                            "total_tokens": _total,
                        },
                    )
                    yield {
                        "type": "usage_delta",
                        "input": _input,
                        "output": _output,
                        "cache_read": _cache_read,
                        "cache_write": 0,
                        "total_tokens": _total,
                    }
                # deltas
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    for candidate in (
                        "reasoning_content",
                        "reasoning",
                        "reasoning_text",
                    ):
                        reasoning_value = getattr(delta, candidate, None)
                        if isinstance(reasoning_value, str) and reasoning_value:
                            _debug(
                                "event",
                                {
                                    "kind": "thinking_delta",
                                    "field": candidate,
                                    "len": len(reasoning_value),
                                },
                            )
                            yield {"type": "thinking_delta", "text": reasoning_value}
                            break
                    reasoning_details = getattr(delta, "reasoning_details", None)
                    if isinstance(reasoning_details, list):
                        for detail in reasoning_details:
                            detail_type = (
                                getattr(detail, "type", None)
                                if not isinstance(detail, dict)
                                else detail.get("type")
                            )
                            detail_id = (
                                getattr(detail, "id", None)
                                if not isinstance(detail, dict)
                                else detail.get("id")
                            )
                            detail_data = (
                                getattr(detail, "data", None)
                                if not isinstance(detail, dict)
                                else detail.get("data")
                            )
                            if (
                                detail_type == "reasoning.encrypted"
                                and isinstance(detail_id, str)
                                and detail_id
                                and isinstance(detail_data, str)
                                and detail_data
                            ):
                                yield {
                                    "type": "tool_call_thought_signature",
                                    "tool_call_id": detail_id,
                                    "thought_signature": __import__("json").dumps(
                                        {
                                            "type": detail_type,
                                            "id": detail_id,
                                            "data": detail_data,
                                        }
                                    ),
                                }
                    text = getattr(delta, "content", None)
                    if isinstance(text, str) and text:
                        emitted_any_text = True
                        _debug(
                            "event",
                            {
                                "kind": "text_delta",
                                "len": len(text),
                                "preview": text[:120],
                            },
                        )
                        yield {"type": "text_delta", "text": text}
                    tool_calls = getattr(delta, "tool_calls", None)
                    if isinstance(tool_calls, list):
                        for tool_call in tool_calls:
                            tool_call_id = getattr(tool_call, "id", None)
                            function = getattr(tool_call, "function", None)
                            tool_call_name = (
                                getattr(function, "name", None)
                                if function is not None
                                else None
                            )
                            tool_call_arguments = (
                                getattr(function, "arguments", None)
                                if function is not None
                                else None
                            )
                            if (
                                isinstance(tool_call_id, str)
                                and tool_call_id
                                and tool_call_id != active_tool_call_id
                            ):
                                if active_tool_call_id is not None:
                                    yield {"type": "tool_call_done"}
                                active_tool_call_id = tool_call_id
                                yield {
                                    "type": "tool_call_start",
                                    "id": tool_call_id,
                                    "name": tool_call_name or "",
                                }
                            if (
                                isinstance(tool_call_arguments, str)
                                and tool_call_arguments
                            ):
                                yield {
                                    "type": "tool_call_args_delta",
                                    "delta": tool_call_arguments,
                                }
                # finish reason
                finish = getattr(choice, "finish_reason", None)
                if isinstance(finish, str):
                    if active_tool_call_id is not None:
                        yield {"type": "tool_call_done"}
                        active_tool_call_id = None
                    # 有些上游在流模式下仅在最后一次返回完整 message.content，而不逐字增量
                    if not emitted_any_text:
                        msg_obj = getattr(choice, "message", None)
                        msg_content = (
                            getattr(msg_obj, "content", None)
                            if msg_obj is not None
                            else None
                        )
                        if isinstance(msg_content, str) and msg_content:
                            emitted_any_text = True
                            _debug(
                                "event",
                                {
                                    "kind": "text_delta_fallback",
                                    "len": len(msg_content),
                                    "preview": msg_content[:120],
                                },
                            )
                            yield {"type": "text_delta", "text": msg_content}
                    mapped = _map_stop_reason(finish)
                    _debug(
                        "event",
                        {"kind": "stop_reason", "raw": finish, "mapped": mapped},
                    )
                    yield {"type": "stop_reason", "stop_reason": mapped}
                    if mapped == "error":
                        yield {
                            "type": "response_error",
                            "message": f"provider finish_reason={finish}",
                        }
            # 正常结束：上游结束迭代后，补发 response_done 以关闭装配器
            if active_tool_call_id is not None:
                yield {"type": "tool_call_done"}
            _debug("stream_done", {})
            yield {"type": "response_done"}
        except Exception as e:
            _debug("stream_iter_error_outer", {"message": str(e)})
            yield provider_error_part(e, source=self.api)
            yield {"type": "response_done"}


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


def _is_supported(status: SupportStatus) -> bool:
    return status is SupportStatus.SUPPORTED


def _map_stop_reason(reason: str) -> str:
    if reason in {"stop", "end"}:
        return "stop"
    if reason == "length":
        return "length"
    if reason in {"function_call", "tool_calls"}:
        return "toolUse"
    if reason in {"content_filter", "network_error"}:
        return "error"
    return "error"


def _apply_prompt_cache_params(
    params: dict[str, Any],
    *,
    protocol: EndpointProtocolFeatures,
    cache_retention: str | None,
    session_id: str | None,
) -> None:
    if cache_retention == "none" or not isinstance(session_id, str) or not session_id:
        return
    if not _is_supported(protocol.cache.prompt_key):
        return
    params["prompt_cache_key"] = session_id
    if cache_retention == "long" and _is_supported(protocol.cache.long_retention):
        params["prompt_cache_retention"] = "24h"


def _apply_reasoning_params(
    params: dict[str, Any],
    extra_body: dict[str, Any],
    *,
    model,
    thinking_format: str | None,
    reasoning_effort: str | None,
    reasoning_effort_map: Mapping[str, str | None],
    supports_reasoning_effort: bool,
    capabilities: object | None = None,
) -> None:
    if not _supports_reasoning(model, capabilities):
        return
    if thinking_format in {"zai", "qwen"}:
        params["enable_thinking"] = bool(reasoning_effort)
        return
    if thinking_format == "moonshot":
        extra_body["thinking"] = {
            "type": "enabled" if isinstance(reasoning_effort, str) else "disabled"
        }
        return
    if thinking_format == "qwen-chat-template":
        params["chat_template_kwargs"] = {
            "enable_thinking": bool(reasoning_effort),
            "preserve_thinking": True,
        }
        return
    if thinking_format == "deepseek":
        params["thinking"] = {
            "type": "enabled" if isinstance(reasoning_effort, str) else "disabled"
        }
        _apply_reasoning_effort_if_supported(
            params,
            reasoning_effort,
            reasoning_effort_map,
            supports_reasoning_effort,
        )
        return
    if thinking_format == "openrouter":
        params["reasoning"] = {
            "effort": _map_reasoning_effort(reasoning_effort, reasoning_effort_map)
            if isinstance(reasoning_effort, str)
            else "none"
        }
        return
    if thinking_format == "together":
        params["reasoning"] = {"enabled": bool(reasoning_effort)}
        _apply_reasoning_effort_if_supported(
            params,
            reasoning_effort,
            reasoning_effort_map,
            supports_reasoning_effort,
        )
        return
    _apply_reasoning_effort_if_supported(
        params,
        reasoning_effort,
        reasoning_effort_map,
        supports_reasoning_effort,
    )


def _apply_reasoning_effort_if_supported(
    params: dict[str, Any],
    reasoning_effort: str | None,
    reasoning_effort_map: Mapping[str, str | None],
    supports_reasoning_effort: bool,
) -> None:
    if isinstance(reasoning_effort, str) and supports_reasoning_effort:
        params["reasoning_effort"] = _map_reasoning_effort(
            reasoning_effort, reasoning_effort_map
        )


def _apply_provider_routing(
    params: dict[str, Any],
    *,
    provider_id: str,
    base_url: str | None,
    request_overrides: Mapping[str, Mapping[str, object]] | None,
) -> None:
    overrides = request_overrides or {}
    namespace = _active_routing_namespace(provider_id, base_url, overrides)
    if namespace is None:
        return
    openrouter_routing = overrides.get("openrouter")
    if namespace == "openrouter" and openrouter_routing:
        params["provider"] = dict(openrouter_routing)
        return
    vercel_gateway_routing = overrides.get("vercelGateway")
    if namespace != "vercelGateway" or not vercel_gateway_routing:
        return
    gateway: dict[str, Any] = {}
    if vercel_gateway_routing.get("only"):
        gateway["only"] = vercel_gateway_routing["only"]
    if vercel_gateway_routing.get("order"):
        gateway["order"] = vercel_gateway_routing["order"]
    if gateway:
        params["providerOptions"] = {"gateway": gateway}


def _active_routing_namespace(
    provider_id: str,
    base_url: str | None,
    request_overrides: Mapping[str, Mapping[str, object]],
) -> str | None:
    if provider_id == "openrouter":
        return "openrouter" if request_overrides.get("openrouter") else None
    if provider_id == "vercel-ai-gateway":
        return "vercelGateway" if request_overrides.get("vercelGateway") else None
    hostname = _base_url_hostname(base_url)
    if hostname == "openrouter.ai" and request_overrides.get("openrouter"):
        return "openrouter"
    if hostname == "ai-gateway.vercel.sh" and request_overrides.get("vercelGateway"):
        return "vercelGateway"
    present = [
        namespace
        for namespace in ("openrouter", "vercelGateway")
        if request_overrides.get(namespace)
    ]
    if len(present) == 1:
        return present[0]
    return None


def _base_url_hostname(base_url: str | None) -> str | None:
    if not isinstance(base_url, str) or not base_url.strip():
        return None
    parsed = urlsplit(base_url if "://" in base_url else f"https://{base_url}")
    return parsed.hostname


def _resolve_timeout_seconds(options, resolved) -> float | int | None:
    option_timeout = get_timeout_seconds(options)
    if isinstance(option_timeout, int | float):
        return option_timeout
    transport_timeout = getattr(
        getattr(resolved, "transport", None),
        "timeout",
        None,
    )
    if isinstance(transport_timeout, int | float) and transport_timeout > 0:
        return transport_timeout
    return None


def _get_cache_control(
    protocol: EndpointProtocolFeatures,
    dialect: EndpointWireDialect,
    cache_retention: str | None,
) -> dict[str, str] | None:
    if dialect.cache.control_format != "anthropic":
        return None
    if cache_retention == "none":
        return None
    ttl = (
        "1h"
        if cache_retention == "long"
        and _is_supported(protocol.cache.long_retention)
        else None
    )
    return {"type": "ephemeral", **({"ttl": ttl} if ttl else {})}


def _apply_anthropic_cache_control(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    cache_control: dict[str, str],
) -> None:
    _add_cache_control_to_system_prompt(messages, cache_control)
    _add_cache_control_to_last_tool(tools, cache_control)
    _add_cache_control_to_last_conversation_message(messages, cache_control)


def _add_cache_control_to_system_prompt(
    messages: list[dict[str, Any]],
    cache_control: dict[str, str],
) -> None:
    for message in messages:
        if message.get("role") in {"system", "developer"}:
            _add_cache_control_to_message(message, cache_control)
            return


def _add_cache_control_to_last_conversation_message(
    messages: list[dict[str, Any]],
    cache_control: dict[str, str],
) -> None:
    for message in reversed(messages):
        if message.get("role") in {"user", "assistant"}:
            if _add_cache_control_to_message(message, cache_control):
                return


def _add_cache_control_to_last_tool(
    tools: list[dict[str, Any]] | None,
    cache_control: dict[str, str],
) -> None:
    if tools:
        tools[-1]["cache_control"] = cache_control


def _add_cache_control_to_message(
    message: dict[str, Any],
    cache_control: dict[str, str],
) -> bool:
    content = message.get("content")
    if isinstance(content, str):
        if not content:
            return False
        message["content"] = [
            {
                "type": "text",
                "text": content,
                "cache_control": cache_control,
            }
        ]
        return True
    if not isinstance(content, list):
        return False
    for part in reversed(content):
        if isinstance(part, dict) and part.get("type") == "text":
            part["cache_control"] = cache_control
            return True
    return False


def _map_reasoning_effort(
    effort: str | None,
    reasoning_effort_map: Mapping[str, str | None],
) -> str | None:
    if not isinstance(effort, str):
        return "none"
    return reasoning_effort_map.get(effort, effort)


def _supports_image_input(model: object, capabilities: object | None = None) -> bool:
    if capabilities is not None:
        return bool(getattr(capabilities, "supports_image_input", False))
    return "image" in getattr(model, "input", ())


def _supports_reasoning(model: object, capabilities: object | None = None) -> bool:
    if capabilities is not None:
        supports_thinking = getattr(capabilities, "supports_thinking", None)
        if supports_thinking is not None:
            return bool(supports_thinking)
        return bool(getattr(capabilities, "reasoning", False))
    return bool(
        getattr(
            model,
            "supports_thinking",
            getattr(model, "reasoning", False),
        )
    )


def _build_messages(
    model,
    normalized: Mapping[str, Any],
    protocol: EndpointProtocolFeatures,
    dialect: EndpointWireDialect,
    capabilities: object | None = None,
) -> list[dict[str, Any]]:
    messages_param: list[dict[str, Any]] = []
    system_prompt = normalized.get("system_prompt")
    supports_developer_role = _is_supported(protocol.roles.developer)
    requires_assistant_after_tool_result = bool(
        dialect.tools.assistant_bridge_required
    )
    if isinstance(system_prompt, str) and system_prompt.strip():
        role = (
            "developer"
            if _supports_reasoning(model, capabilities) and supports_developer_role
            else "system"
        )
        messages_param.append(
            {"role": role, "content": sanitize_surrogates(system_prompt)}
        )

    messages = normalized.get("messages", [])
    last_role: str | None = None
    index = 0
    while index < len(messages):
        msg = messages[index]
        message_role = _message_role(msg)
        if (
            requires_assistant_after_tool_result
            and last_role == "toolResult"
            and message_role == "user"
        ):
            messages_param.append(
                {
                    "role": "assistant",
                    "content": TOOL_RESULTS_PROCESSED_ASSISTANT_TEXT,
                }
            )
            last_role = "assistant"
        if message_role == "user":
            payload = _user_message_payload(msg, model, capabilities)
            if payload is not None:
                messages_param.append(payload)
                last_role = "user"
            index += 1
            continue
        if message_role == "assistant":
            payload = _assistant_message_payload(msg, dialect, model, capabilities)
            if payload is not None:
                messages_param.append(payload)
                last_role = "assistant"
            index += 1
            continue
        if message_role == "toolResult":
            image_blocks: list[dict[str, Any]] = []
            while (
                index < len(messages) and _message_role(messages[index]) == "toolResult"
            ):
                tool_payload, tool_images = _tool_result_payload(
                    messages[index],
                    dialect,
                    model,
                    capabilities,
                )
                messages_param.append(tool_payload)
                image_blocks.extend(tool_images)
                index += 1
            if image_blocks:
                if requires_assistant_after_tool_result:
                    messages_param.append(
                        {
                            "role": "assistant",
                            "content": TOOL_RESULTS_PROCESSED_ASSISTANT_TEXT,
                        }
                    )
                messages_param.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Attached image(s) from tool result:",
                            },
                            *image_blocks,
                        ],
                    }
                )
                last_role = "user"
            else:
                last_role = "toolResult"
            continue
        index += 1
    return messages_param


def _build_tools(
    tools: Sequence[Tool] | None,
    protocol: EndpointProtocolFeatures,
) -> list[dict[str, Any]] | None:
    if not isinstance(tools, Sequence) or isinstance(tools, str) or not tools:
        return None
    supports_strict_mode = _is_supported(protocol.tools.strict_schema)
    payload: list[dict[str, Any]] = []
    for tool in tools:
        function_payload = {
            "name": tool.name,
            "description": tool.description,
            "parameters": sanitize_tool_parameters(tool.parameters),
        }
        if supports_strict_mode:
            function_payload["strict"] = False
        payload.append({"type": "function", "function": function_payload})
    return payload


def _has_tool_history(messages: list[object]) -> bool:
    for msg in messages:
        role = _message_role(msg)
        if role == "toolResult":
            return True
        if role == "assistant" and isinstance(msg, AssistantMessage):
            if any(getattr(block, "type", None) == "toolCall" for block in msg.content):
                return True
    return False


def _message_role(message: object) -> str | None:
    return getattr(message, "role", None)


def _user_message_payload(
    message: object, model, capabilities: object | None = None
) -> dict[str, Any] | None:
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return None
    parts: list[dict[str, Any]] = []
    text_fragments: list[str] = []
    for part in content:
        part_type = _part_type(part)
        if part_type == "text":
            text = _part_text(part)
            if isinstance(text, str) and text.strip():
                sanitized_text = sanitize_surrogates(text)
                text_fragments.append(sanitized_text)
                parts.append({"type": "text", "text": sanitized_text})
        elif part_type == "image" and _supports_image_input(model, capabilities):
            data = _part_data(part)
            mime_type = _part_mime_type(part)
            if (
                isinstance(data, str)
                and data
                and isinstance(mime_type, str)
                and mime_type
            ):
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{data}"},
                    }
                )
    if not parts:
        return None
    if len(parts) == len(text_fragments) and text_fragments:
        return {"role": "user", "content": "\n".join(text_fragments)}
    return {"role": "user", "content": parts}


def _assistant_message_payload(
    message: object,
    dialect: EndpointWireDialect,
    model,
    capabilities: object | None = None,
) -> dict[str, Any] | None:
    requires_assistant_after_tool_result = bool(
        dialect.tools.assistant_bridge_required
    )
    requires_thinking_as_text = bool(dialect.reasoning.thinking_as_text)
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return None
    text_blocks: list[str] = []
    thinking_blocks: list[tuple[str, str | None]] = []
    tool_calls: list[dict[str, Any]] = []
    reasoning_details: list[dict[str, Any]] = []
    for part in content:
        part_type = _part_type(part)
        if part_type == "text":
            text = _part_text(part)
            if isinstance(text, str) and text.strip():
                text_blocks.append(sanitize_surrogates(text))
        elif part_type == "thinking":
            thinking = getattr(part, "thinking", None)
            signature = getattr(part, "thinking_signature", None)
            if isinstance(thinking, str) and thinking.strip():
                thinking_blocks.append(
                    (
                        sanitize_surrogates(thinking),
                        signature if isinstance(signature, str) else None,
                    )
                )
        elif part_type == "toolCall":
            tool_id = getattr(part, "id", None)
            tool_name = getattr(part, "name", None)
            tool_args = getattr(part, "arguments", {}) or {}
            if isinstance(tool_id, str) and tool_id:
                tool_calls.append(
                    {
                        "id": tool_id,
                        "type": "function",
                        "function": {
                            "name": tool_name or "",
                            "arguments": __import__("json").dumps(tool_args),
                        },
                    }
                )
                thought_signature = getattr(part, "thought_signature", None)
                if isinstance(thought_signature, str) and thought_signature:
                    try:
                        reasoning_details.append(
                            __import__("json").loads(thought_signature)
                        )
                    except Exception:
                        pass
    assistant_content = (
        "".join(text_blocks)
        if text_blocks
        else ("" if requires_assistant_after_tool_result else None)
    )
    payload: dict[str, Any] = {"role": "assistant", "content": assistant_content}
    if thinking_blocks:
        thinking_text = "\n\n".join(block for block, _ in thinking_blocks)
        if requires_thinking_as_text:
            payload["content"] = f"{thinking_text}{assistant_content or ''}"
        else:
            for _, signature in thinking_blocks:
                if isinstance(signature, str) and signature:
                    payload[signature] = thinking_text
                    break
    if tool_calls:
        payload["tool_calls"] = tool_calls
    if reasoning_details:
        payload["reasoning_details"] = reasoning_details
    if (
        dialect.reasoning.assistant_content_required
        and _supports_reasoning(model, capabilities)
        and "reasoning_content" not in payload
    ):
        payload["reasoning_content"] = ""
    content_value = payload.get("content")
    has_content = content_value is not None and (
        not isinstance(content_value, str) or content_value != ""
    )
    if not has_content and not tool_calls and not payload.keys() - {"role", "content"}:
        return None
    if payload.get("content") == "" and not requires_assistant_after_tool_result:
        payload["content"] = None
    if payload.get("content") == "" and not tool_calls:
        return None
    return payload


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


def _tool_result_payload(
    message: object,
    dialect: EndpointWireDialect,
    model,
    capabilities: object | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    assert isinstance(message, ToolResultMessage)
    text_parts = [
        sanitize_surrogates(part.text)
        for part in message.content
        if isinstance(part, TextPart) and part.text.strip()
    ]
    text_result = "\n".join(text_parts)
    has_images = any(_part_type(part) == "image" for part in message.content)
    image_blocks: list[dict[str, Any]] = []
    if _supports_image_input(model, capabilities):
        for part in message.content:
            if _part_type(part) != "image":
                continue
            data = _part_data(part)
            mime_type = _part_mime_type(part)
            if (
                isinstance(data, str)
                and data
                and isinstance(mime_type, str)
                and mime_type
            ):
                image_blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{data}"},
                    }
                )
    tool_payload = {
        "role": "tool",
        "tool_call_id": message.tool_call_id,
        "content": text_result
        or ("(see attached image)" if has_images else MISSING_TOOL_RESULT_TEXT),
    }
    if dialect.tools.result_name_required and message.tool_name:
        tool_payload["name"] = message.tool_name
    return tool_payload, image_blocks


def _part_type(part: object) -> str | None:
    return getattr(part, "type", None)


def _part_text(part: object) -> str | None:
    return getattr(part, "text", None)


def _part_data(part: object) -> str | None:
    return getattr(part, "data", None)


def _part_mime_type(part: object) -> str | None:
    return getattr(part, "mime_type", None)
