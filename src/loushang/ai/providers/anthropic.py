from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from loushang.ai.context import ensure_normalized_context
from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.model.compat_schema import (
    SEND_SESSION_AFFINITY_HEADERS,
    SUPPORTS_LONG_CACHE_RETENTION,
    compat_bool,
)
from loushang.ai.options import PairingMode
from loushang.ai.output_budget import resolve_output_token_budget
from loushang.ai.provider import resolve_request_for_model
from loushang.ai.provider.cancellation import is_signal_cancelled
from loushang.ai.provider.errors import provider_error_part
from loushang.ai.providers.anthropic_base import AnthropicProviderBase
from loushang.ai.providers.provider_helpers import (
    apply_session_headers,
    extract_sdk_api_key,
    sdk_default_headers,
)
from loushang.ai.tool import to_anthropic_tools
from loushang.ai.tool.helpers import (
    compute_remaining_context,
    estimate_tokens_simple_from_messages,
)
from loushang.ai.trace import emit_trace as _emit_trace
from loushang.ai.utils import parse_streaming_json, sanitize_surrogates


def _build_anthropic_message_payloads(
    normalized: dict[str, Any],
    *,
    is_oauth_token: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, str]] | None]:
    messages_param: list[dict[str, Any]] = []
    system_param = None
    system_prompt = normalized.get("system_prompt")
    if isinstance(system_prompt, str) and system_prompt.strip():
        system_param = [{"type": "text", "text": sanitize_surrogates(system_prompt)}]
    for msg in normalized.get("messages", []):
        role = (
            getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
        )
        if role == "user":
            content = (
                getattr(msg, "content", None)
                if not isinstance(msg, dict)
                else msg.get("content")
            )
            if isinstance(content, list):
                user_blocks: list[dict[str, object]] = []
                for p in content:
                    ptype = (
                        getattr(p, "type", None)
                        if not isinstance(p, dict)
                        else p.get("type")
                    )
                    if ptype == "text":
                        txt = (
                            getattr(p, "text", "")
                            if not isinstance(p, dict)
                            else p.get("text", "")
                        )
                        if isinstance(txt, str) and txt.strip():
                            user_blocks.append(
                                {"type": "text", "text": sanitize_surrogates(txt)}
                            )
                    elif ptype == "image":
                        data = (
                            getattr(p, "data", "")
                            if not isinstance(p, dict)
                            else p.get("data", "")
                        )
                        mime = (
                            getattr(p, "mime_type", "")
                            if not isinstance(p, dict)
                            else p.get("mimeType", "")
                        )
                        if (
                            isinstance(data, str)
                            and data
                            and isinstance(mime, str)
                            and mime
                        ):
                            user_blocks.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime,
                                        "data": data,
                                    },
                                }
                            )
                if user_blocks:
                    messages_param.append({"role": "user", "content": user_blocks})
        elif role == "assistant":
            content = (
                getattr(msg, "content", None)
                if not isinstance(msg, dict)
                else msg.get("content")
            )
            if isinstance(content, list):
                assistant_blocks: list[dict[str, object]] = []
                for p in content:
                    ptype = (
                        getattr(p, "type", None)
                        if not isinstance(p, dict)
                        else p.get("type")
                    )
                    if ptype == "image":
                        data = (
                            getattr(p, "data", "")
                            if not isinstance(p, dict)
                            else p.get("data", "")
                        )
                        mime = (
                            getattr(p, "mime_type", "")
                            if not isinstance(p, dict)
                            else p.get("mimeType", "")
                        )
                        if (
                            isinstance(data, str)
                            and data
                            and isinstance(mime, str)
                            and mime
                        ):
                            assistant_blocks.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime,
                                        "data": data,
                                    },
                                }
                            )
                        continue
                    payload = (
                        AnthropicProviderBase.assistant_block_to_anthropic_payload(p)
                    )
                    if payload is not None:
                        if is_oauth_token and payload.get("type") == "tool_use":
                            payload = {
                                **payload,
                                "name": AnthropicProviderBase.to_oauth_tool_name(
                                    str(payload.get("name", ""))
                                ),
                            }
                        assistant_blocks.append(payload)
                if assistant_blocks:
                    messages_param.append(
                        {"role": "assistant", "content": assistant_blocks}
                    )
        elif role == "toolResult":
            tool_call_id = (
                getattr(msg, "tool_call_id", None)
                if not isinstance(msg, dict)
                else msg.get("toolCallId") or msg.get("tool_call_id")
            )
            is_error = (
                getattr(msg, "is_error", None)
                if not isinstance(msg, dict)
                else msg.get("isError")
            )
            content = (
                getattr(msg, "content", None)
                if not isinstance(msg, dict)
                else msg.get("content")
            )
            if isinstance(tool_call_id, str) and tool_call_id:
                _append_tool_result_payload(
                    messages_param,
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": AnthropicProviderBase.tool_result_content_to_anthropic_payload(
                            content
                        ),
                        "is_error": bool(is_error),
                    },
                )
    return messages_param, system_param


def _append_tool_result_payload(
    messages_param: list[dict[str, Any]],
    tool_result: dict[str, Any],
) -> None:
    if messages_param:
        previous = messages_param[-1]
        previous_content = previous.get("content")
        if (
            previous.get("role") == "user"
            and isinstance(previous_content, list)
            and previous_content
            and all(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in previous_content
            )
        ):
            previous_content.append(tool_result)
            return
    messages_param.append({"role": "user", "content": [tool_result]})


def _tool_input_to_json_delta(value: object) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        if not value:
            return None
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return None


_MISSING = object()


def _summarize_tool_input(value: object) -> dict[str, object]:
    if value is _MISSING:
        return {"present": False}
    if value is None:
        return {"present": True, "kind": "none"}
    if isinstance(value, dict):
        summary: dict[str, object] = {
            "present": True,
            "kind": "object",
            "keys": list(value.keys()),
            "empty": not bool(value),
        }
        path = value.get("path") or value.get("file_path")
        if isinstance(path, str):
            summary["path"] = _summarize_sdk_string(path)
        content = value.get("content")
        if isinstance(content, str):
            summary["content_chars"] = len(content)
        return summary
    if isinstance(value, str):
        return {
            "present": True,
            "kind": "string",
            "chars": len(value),
            "preview": _summarize_sdk_string(value),
        }
    return {
        "present": True,
        "kind": type(value).__name__,
        "value": _summarize_sdk_value(value),
    }


def _summarize_tool_snapshot(snapshot: object) -> dict[str, object]:
    return {
        "type": getattr(snapshot, "type", None),
        "input": _summarize_tool_input(getattr(snapshot, "input", _MISSING)),
    }


def _summarize_tool_delta(delta: object) -> dict[str, object]:
    summary: dict[str, object] = {"type": getattr(delta, "type", None)}
    partial = getattr(delta, "partial_json", None)
    if isinstance(partial, str):
        summary["partial_chars"] = len(partial)
        summary["partial_preview"] = _summarize_sdk_string(partial)
    return summary


def _summarize_tool_args_json(raw: str) -> dict[str, object]:
    summary: dict[str, object] = {"chars": len(raw)}
    if not raw:
        return {**summary, "valid_json": False, "error": "empty"}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        repaired = parse_streaming_json(raw)
        repair_summary: dict[str, object] = {"repair_valid": bool(repaired)}
        if repaired:
            repair_summary.update(
                {
                    "repaired_keys": list(repaired.keys()),
                    "repaired_path": repaired.get("path") or repaired.get("file_path"),
                    "repaired_content_chars": len(repaired["content"])
                    if isinstance(repaired.get("content"), str)
                    else None,
                }
            )
        return {
            **summary,
            "valid_json": False,
            "error": f"{error.msg} at {error.pos}",
            **repair_summary,
            "prefix": _summarize_sdk_string(raw[:240]),
            "around_error": _summarize_sdk_string(
                raw[max(0, error.pos - 120) : error.pos + 120]
            ),
            "suffix": _summarize_sdk_string(raw[-240:]),
        }
    if not isinstance(parsed, dict):
        return {
            **summary,
            "valid_json": True,
            "kind": type(parsed).__name__,
        }
    return {
        **summary,
        "valid_json": True,
        "kind": "object",
        "keys": list(parsed.keys()),
        "path": parsed.get("path") or parsed.get("file_path"),
        "content_chars": len(parsed["content"])
        if isinstance(parsed.get("content"), str)
        else None,
    }


def _summarize_sdk_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _summarize_sdk_string(value)
    if isinstance(value, dict):
        return {str(key): _summarize_sdk_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_summarize_sdk_value(item) for item in value[:20]]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(exclude_none=True)
            if isinstance(dumped, dict):
                return _summarize_sdk_value(dumped)
        except Exception:
            pass

    attrs = getattr(value, "__dict__", None)
    if isinstance(attrs, dict):
        return {
            key: _summarize_sdk_value(item)
            for key, item in attrs.items()
            if not key.startswith("_")
        }
    return repr(value)


def _summarize_sdk_string(value: str) -> str:
    if len(value) <= 240:
        return value
    return f"{value[:160]}...<{len(value)} chars>"


class AnthropicProvider(AnthropicProviderBase):
    api = "anthropic-messages"

    def __init__(self, *, client: Any | None = None) -> None:
        # 允许注入自建客户端（同步或异步），否则按需创建
        self._client = client

    async def stream(self, model, context, options):
        """
        Anthropic 官方 SDK 适配版流接口（可选实现）。
        注意：需要安装 `anthropic` 包；否则会在创建客户端时报错。
        """
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

        """
        将 Anthropic SDK 的 streaming 事件映射到 RawPart。
        当前实现覆盖文本、thinking、signature、redacted thinking、工具增量、usage、stop_reason 与完成事件。
        """

        def _debug(event: str, data: dict | None = None) -> None:
            payload = {"type": f"sdk:{event}"}
            if data:
                for key, value in data.items():
                    payload["event_type" if key == "type" else key] = value
            _emit_trace(options, payload)

        normalized = ensure_normalized_context(
            context,
            model=model,
            pairing_mode=_pairing_mode(),
        )
        resolved = resolve_request_for_model(model, options=options)
        compat = dict(getattr(resolved, "compat", {}) or {})

        headers = resolved.headers or {}
        api_key = extract_sdk_api_key(
            headers,
            prefer_x_api_key=True,
            error_message=(
                "Anthropic SDK provider requires an API key "
                "(x-api-key or Authorization: Bearer)"
            ),
        )

        # 延迟导入官方 SDK，避免未安装时报错影响其它路径
        try:
            from anthropic import AsyncAnthropic  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "anthropic SDK is not installed. Install via `pip install anthropic`"
            ) from e

        # 仅透传非鉴权头作为默认头（如 anthropic-version），鉴权用 api_key 参数避免重复
        default_headers = sdk_default_headers(headers)
        # 门闸：按 compat/headers 决定是否注入 beta（与 httpx 对齐）
        need_ilt = self.should_inject_interleaved_thinking(
            model_id=model.id,
            options=options,
            compat=compat,
        )
        need_fg = self.should_inject_fine_grained_tools(
            compat=compat,
            headers=default_headers,
        )
        if need_ilt or need_fg:
            default_headers = self.apply_beta_headers(
                existing_headers=default_headers,
                need_interleaved_beta=need_ilt,
                force_fine_grained_tools=need_fg,
            )

        is_oauth_token = False
        # OAuth/Copilot 身份头（对齐 pi-ai OAuth 路径）
        is_oauth_token = self.is_oauth_token(api_key)
        if is_oauth_token:
            default_headers = self.apply_oauth_identity_headers(default_headers)
        cache_retention = (
            getattr(options, "cache_retention", None) if options is not None else None
        )
        session_id = (
            getattr(options, "session_id", None) if options is not None else None
        )
        if (
            cache_retention != "none"
            and isinstance(session_id, str)
            and session_id
            and compat_bool(compat, SEND_SESSION_AFFINITY_HEADERS)
        ):
            apply_session_headers(
                default_headers,
                session_id,
                include_affinity=True,
            )

        client = self._client or AsyncAnthropic(  # type: ignore[call-arg]
            api_key=api_key,
            base_url=resolved.base_url,
            default_headers=default_headers or None,
        )
        _debug("client", {"base_url": resolved.base_url, "headers": default_headers})

        messages_param, system_param = _build_anthropic_message_payloads(
            normalized,
            is_oauth_token=is_oauth_token,
        )

        tools_param = None
        if normalized.get("tools"):
            tools_param = []
            for t in to_anthropic_tools(normalized["tools"]):
                tools_param.append(
                    {
                        "name": self.to_oauth_tool_name(str(t.get("name", "")))
                        if is_oauth_token
                        else t.get("name"),
                        "description": t.get("description"),
                        "input_schema": t.get("input_schema"),
                    }
                )

        max_tokens = resolve_output_token_budget(model, resolved, options).value
        thinking_cfg: dict[str, object] | None = None
        # 思考模式：自适应或预算式；与 temperature 互斥
        try:
            want_thinking = normalized.get("emit_thinking") or (
                options is not None and getattr(options, "thinking_enabled", False)
            )
            if want_thinking:
                if self.supports_adaptive_thinking(model.id):
                    thinking_cfg = {"type": "adaptive"}
                    # effort 由 reasoning 等级映射
                    effort = self.map_thinking_level_to_effort(
                        getattr(options, "effort", None), model.id
                    )  # effort 可直接来自 options.effort
                    if effort is None:
                        reasoning = getattr(options, "reasoning", None)
                        effort = self.map_thinking_level_to_effort(reasoning, model.id)
                    # 将 effort 合并到 output_config
                    if effort:
                        try:
                            # 在 params 构造后统一注入
                            pass
                        except Exception:
                            pass
                else:
                    thinking_budget_tokens = getattr(
                        options, "thinking_budget_tokens", None
                    )
                    thinking_cfg = {
                        "type": "enabled",
                        "budget_tokens": thinking_budget_tokens
                        if isinstance(thinking_budget_tokens, int)
                        else 1024,
                    }
                # 与思考互斥：移除 temperature
                if (
                    options is not None
                    and getattr(options, "temperature", None) is not None
                ):
                    pass  # 不放入 params（下方设置时跳过）
        except Exception:
            pass

        params: dict[str, Any] = {
            "model": model.id,
            "messages": messages_param,
            "max_tokens": max(1, int(max_tokens)),
        }
        if system_param:
            params["system"] = system_param
        if tools_param:
            params["tools"] = tools_param
        if thinking_cfg:
            params["thinking"] = thinking_cfg
        # 若存在自适应思考的 effort，注入 output_config
        want_thinking = normalized.get("emit_thinking") or (
            options is not None and getattr(options, "thinking_enabled", False)
        )
        if want_thinking and self.supports_adaptive_thinking(model.id):
            effort = self.map_thinking_level_to_effort(
                getattr(options, "effort", None), model.id
            )
            if effort is None:
                reasoning = getattr(options, "reasoning", None)
                effort = self.map_thinking_level_to_effort(reasoning, model.id)
            if effort:
                params["output_config"] = {"effort": effort}
        # 透传 tool_choice（auto/any/none 或 {type:'tool', name:...}）
        tool_choice = getattr(options, "tool_choice", None)
        if tool_choice is not None:
            if isinstance(tool_choice, str):
                params["tool_choice"] = {"type": tool_choice}
            elif isinstance(tool_choice, dict) and "type" in tool_choice:
                params["tool_choice"] = tool_choice
        # 注入 cache_control（system/最后一个 user）
        cc = self.get_cache_control(
            base_url=resolved.base_url,
            cache_retention=getattr(options, "cache_retention", None)
            if options is not None
            else None,
            supports_long_cache_retention=compat_bool(
                compat, SUPPORTS_LONG_CACHE_RETENTION, default=True
            ),
        )
        cache_control = cc.get("cacheControl")
        if cache_control:
            if isinstance(params.get("system"), list) and params["system"]:
                last = params["system"][-1]
                if isinstance(last, dict):
                    last.setdefault("cache_control", cache_control)
            # 最后一个 user 消息
            for m in reversed(params.get("messages", [])):
                if isinstance(m, dict) and m.get("role") == "user":
                    content = m.get("content")
                    if isinstance(content, list) and content:
                        lb = content[-1]
                        if isinstance(lb, dict) and lb.get("type") in {
                            "text",
                            "image",
                            "tool_result",
                        }:
                            lb.setdefault("cache_control", cache_control)
                    break
        # metadata.user_id 透传
        meta = getattr(options, "metadata", None) if options is not None else None
        user_id = meta.get("user_id") if isinstance(meta, dict) else None
        if isinstance(user_id, str) and user_id:
            params["metadata"] = {"user_id": user_id}
        # temperature：仅在未启用思考时设置
        if (
            not thinking_cfg
            and options is not None
            and getattr(options, "temperature", None) is not None
        ):
            params["temperature"] = options.temperature
        # Clamp max_tokens by remaining context if capability provides window
        remaining = compute_remaining_context(
            getattr(model, "context_window", None),
            estimate_tokens_simple_from_messages(normalized.get("messages", [])),
            safety_margin=64,
        )
        if remaining is not None and isinstance(params.get("max_tokens"), int):
            before = params["max_tokens"]
            params["max_tokens"] = max(1, min(before, remaining))
            _emit_trace(
                options,
                {
                    "type": "clamp",
                    "api": resolved.api,
                    "provider": model.provider_id,
                    "field": "max_tokens",
                    "before": before,
                    "after": params["max_tokens"],
                    "remaining": remaining,
                },
            )

        _debug(
            "payload", {"params": {k: v for k, v in params.items() if k != "messages"}}
        )

        # on_payload 钩子
        try:
            onp = getattr(options, "on_payload", None) if options is not None else None
            if callable(onp):
                next_params = onp(params, model)  # 允许返回替换
                if asyncio.iscoroutine(next_params):
                    next_params = await next_params
                if next_params:
                    params = next_params  # type: ignore[assignment]
        except Exception as e:
            _debug("on_payload_error", {"message": str(e)})

        try:
            stream_ctx = client.messages.stream(**params)
        except Exception as e:
            _debug("stream_error", {"message": str(e)})
            yield provider_error_part(e, source=self.api)
            return
        await _notify_provider_response(options, stream_ctx, model)
        # 启动事件：发出 response_start（若 SDK 提供 id 会在后续 message_start 拿到）
        # 主循环（SDK 为 async context manager）
        active_tool_block = False
        active_tool_args_from_start = False
        active_tool_arg_chunks: list[str] = []
        active_tool_id: str | None = None
        active_tool_name: str | None = None
        active_tool_args_source = "none"
        active_tool_delta_chars = 0
        active_tool_last_delta: dict[str, object] | None = None
        active_tool_last_snapshot: dict[str, object] | None = None
        try:
            async with stream_ctx as stream:
                async for event in stream:
                    etype = getattr(event, "type", None)
                    if etype == "message_start":
                        msg = getattr(event, "message", None)
                        rid = getattr(msg, "id", None)
                        if isinstance(rid, str):
                            yield {"type": "response_start", "response_id": rid}
                        usage = getattr(msg, "usage", None)
                        if usage:
                            yield {
                                "type": "usage_delta",
                                "input": getattr(usage, "input_tokens", 0) or 0,
                                "output": getattr(usage, "output_tokens", 0) or 0,
                                "cache_read": getattr(
                                    usage, "cache_read_input_tokens", 0
                                )
                                or 0,
                                "cache_write": getattr(
                                    usage, "cache_creation_input_tokens", 0
                                )
                                or 0,
                                "total_tokens": 0,
                            }
                        continue
                    if etype == "content_block_start":
                        cblk = getattr(event, "content_block", None)
                        active_tool_block = False
                        active_tool_args_from_start = False
                        active_tool_arg_chunks = []
                        active_tool_id = None
                        active_tool_name = None
                        active_tool_args_source = "none"
                        active_tool_delta_chars = 0
                        active_tool_last_delta = None
                        active_tool_last_snapshot = None
                        # text/thinking/tool_use 起始：我们只需开始时打标，增量通过 delta 下发
                        # 目前 RawAssembler 不依赖 *_start 事件，故不强制发送 start，减少噪音
                        if (
                            cblk is not None
                            and getattr(cblk, "type", None) == "tool_use"
                        ):
                            # 记录开始，立刻发出 tool_call_start
                            tid = getattr(cblk, "id", None)
                            tname = getattr(cblk, "name", None)
                            if isinstance(tid, str) and isinstance(tname, str) and tid:
                                active_tool_block = True
                                active_tool_id = tid
                                active_tool_name = (
                                    self.from_oauth_tool_name(
                                        tname, normalized.get("tools")
                                    )
                                    if is_oauth_token
                                    else tname
                                )
                                input_value = getattr(cblk, "input", _MISSING)
                                _debug(
                                    "tool_start",
                                    {
                                        "id": active_tool_id,
                                        "name": active_tool_name,
                                        "input": _summarize_tool_input(input_value),
                                    },
                                )
                                yield {
                                    "type": "tool_call_start",
                                    "id": tid,
                                    "name": active_tool_name,
                                }
                                input_delta = _tool_input_to_json_delta(input_value)
                                if input_delta:
                                    active_tool_args_from_start = True
                                    active_tool_args_source = "content_block.input"
                                    active_tool_arg_chunks = [input_delta]
                                    yield {
                                        "type": "tool_call_args_delta",
                                        "delta": input_delta,
                                    }
                        elif (
                            cblk is not None
                            and getattr(cblk, "type", None) == "redacted_thinking"
                        ):
                            signature = getattr(cblk, "data", None)
                            if isinstance(signature, str) and signature:
                                yield {
                                    "type": "redacted_thinking",
                                    "signature": signature,
                                }
                        continue
                    if etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if active_tool_block:
                            snapshot = getattr(event, "snapshot", None)
                            if snapshot is not None:
                                active_tool_last_snapshot = _summarize_tool_snapshot(
                                    snapshot
                                )
                        if (
                            delta is not None
                            and getattr(delta, "type", None) == "text_delta"
                        ):
                            text = getattr(delta, "text", None)
                            if isinstance(text, str) and text:
                                yield {"type": "text_delta", "text": text}
                        elif (
                            delta is not None
                            and getattr(delta, "type", None) == "thinking_delta"
                        ):
                            thinking_text = getattr(delta, "thinking", None)
                            if isinstance(thinking_text, str) and thinking_text:
                                # RawAssembler 期望键名为 text
                                yield {"type": "thinking_delta", "text": thinking_text}
                        elif (
                            delta is not None
                            and getattr(delta, "type", None) == "signature_delta"
                        ):
                            signature = getattr(delta, "signature", None)
                            if isinstance(signature, str) and signature:
                                yield {
                                    "type": "thinking_signature_delta",
                                    "signature": signature,
                                }
                        elif (
                            delta is not None
                            and getattr(delta, "type", None) == "input_json_delta"
                        ):
                            partial = getattr(delta, "partial_json", None)
                            if isinstance(partial, str) and partial:
                                active_tool_block = True
                                active_tool_delta_chars += len(partial)
                                active_tool_last_delta = _summarize_tool_delta(delta)
                                if not active_tool_args_from_start:
                                    active_tool_args_source = "input_json_delta"
                                    active_tool_arg_chunks.append(partial)
                                    yield {
                                        "type": "tool_call_args_delta",
                                        "delta": partial,
                                    }
                        elif active_tool_block and delta is not None:
                            active_tool_last_delta = _summarize_tool_delta(delta)
                        continue
                    if etype == "content_block_stop":
                        # 工具块结束：发出 tool_call_done（不带 payload，RawAssembler 内部汇总参数）
                        if active_tool_block:
                            tool_trace = {
                                "id": active_tool_id,
                                "name": active_tool_name,
                                "args_source": active_tool_args_source,
                                "delta_chars": active_tool_delta_chars,
                                "args": _summarize_tool_args_json(
                                    "".join(active_tool_arg_chunks)
                                ),
                            }
                            if active_tool_args_source == "none":
                                tool_trace["last_delta"] = active_tool_last_delta
                                tool_trace["last_snapshot"] = active_tool_last_snapshot
                                _debug("tool_empty_args", tool_trace)
                            else:
                                _debug("tool_done", tool_trace)
                            yield {"type": "tool_call_done"}
                            active_tool_block = False
                            active_tool_args_from_start = False
                            active_tool_arg_chunks = []
                            active_tool_id = None
                            active_tool_name = None
                            active_tool_args_source = "none"
                            active_tool_delta_chars = 0
                            active_tool_last_delta = None
                            active_tool_last_snapshot = None
                        continue
                    if etype == "message_delta":
                        delta = getattr(event, "delta", None)
                        stop_reason = getattr(delta, "stop_reason", None)
                        if isinstance(stop_reason, str):
                            mapped = _map_stop_reason(stop_reason)
                            yield {"type": "stop_reason", "stop_reason": mapped}
                            if mapped == "error":
                                yield {
                                    "type": "response_error",
                                    "message": f"provider stop_reason={stop_reason}",
                                }
                        usage = getattr(event, "usage", None)
                        if usage:
                            yield {
                                "type": "usage_delta",
                                "input": getattr(usage, "input_tokens", 0) or 0,
                                "output": getattr(usage, "output_tokens", 0) or 0,
                                "cache_read": getattr(
                                    usage, "cache_read_input_tokens", 0
                                )
                                or 0,
                                "cache_write": getattr(
                                    usage, "cache_creation_input_tokens", 0
                                )
                                or 0,
                                "total_tokens": (getattr(usage, "input_tokens", 0) or 0)
                                + (getattr(usage, "output_tokens", 0) or 0),
                            }
                        continue
                    if etype == "message_stop":
                        # 若 provider 报告需要工具但未下发细粒度工具流，做提示（兜底策略可后续扩展）
                        # 这里不阻断 response_done，只发出 debug error 便于定位
                        # 具体 fallback（同步调用/非流式拉取）作为后续增强
                        yield {"type": "response_done"}
                        continue
                    if etype == "error":
                        err = getattr(event, "error", None)
                        msg = getattr(err, "message", None) if err is not None else None
                        yield {
                            "type": "response_error",
                            "message": msg or "Unknown error",
                        }
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


def _map_stop_reason(reason: str) -> str:
    if reason == "max_tokens":
        return "length"
    if reason in {"end_turn", "stop_sequence", "pause_turn"}:
        return "stop"
    if reason == "tool_use":
        return "toolUse"
    if reason in {"refusal", "sensitive"}:
        return "error"
    raise ValueError(f"Unhandled stop reason: {reason}")
