from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from dataclasses import dataclass
from inspect import isawaitable
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from loushang.ai.contrib.openai_codex.runtime_config import (
    OpenAICodexRuntimeConfig,
    resolve_openai_codex_runtime_config,
)
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.model.domain import OpenAIResponsesConfig
from loushang.ai.options import (
    get_reasoning_effort,
    get_reasoning_summary,
    get_timeout_seconds,
)
from loushang.ai.provider import ProviderRequest
from loushang.ai.provider.errors import (
    provider_error_part,
    provider_error_part_from_raw,
)
from loushang.ai.providers.openai_responses_shared import (
    convert_responses_messages,
    convert_responses_tools,
    process_responses_stream,
)
from loushang.ai.structured import openai_responses_text_format
from loushang.ai.trace import emit_trace as _emit_trace
from loushang.ai.utils import sanitize_surrogates


class OpenAICodexResponsesProvider:
    api = "openai-codex-responses"
    supports_structured_output = True
    adapter_config_resolver = staticmethod(resolve_openai_codex_runtime_config)

    def __init__(
        self, *, client: Any | None = None, websocket_cache_ttl_ms: int = 5 * 60 * 1000
    ) -> None:
        self._client = client
        self._websocket_session_cache: dict[str, _CachedWebSocketConnection] = {}
        self._websocket_cache_ttl_ms = websocket_cache_ttl_ms

    async def stream_raw(self, request: ProviderRequest) -> AsyncIterator[RawPart]:
        model = request.model
        options = request.options
        resolved = request

        def _debug(event: str, data: dict | None = None) -> None:
            _emit_trace(options, {"type": f"sdk:{event}", **(data or {})})
            import os

            if os.getenv("LOUSHANG_DEBUG") == "1":
                with suppress(Exception):
                    print(f"[sdk:{event}] {data or {}}")

        normalized = request.context
        headers = dict(resolved.headers or {})
        codex_config = _codex_runtime_config(resolved.adapter_config)

        api_key = _extract_api_key(headers)
        account_id = _resolve_account_id(
            headers,
            api_key=api_key,
            auth_account_id=getattr(resolved, "auth_account_id", None),
        )
        body = _build_request_body(
            model,
            normalized,
            options,
            codex_config=codex_config,
            capabilities=getattr(resolved, "capabilities", None),
            upstream_model_id=getattr(resolved, "upstream_model_id", None),
        )
        url = _resolve_codex_url(resolved.base_url)
        session_id = getattr(options, "session_id", None)
        request_headers = _build_sse_headers(
            headers,
            api_key=api_key,
            account_id=account_id,
            session_id=session_id,
            codex_config=codex_config,
        )
        _debug(
            "client",
            {
                "base_url": resolved.base_url,
                "headers": _redact_headers(request_headers),
            },
        )
        _debug(
            "payload",
            {
                "params": _request_body_trace_summary(body),
            },
        )

        owned_client = None
        client = self._client
        if client is None:
            owned_client = _HttpxCodexClient()
            client = owned_client
        try:
            transport = getattr(options, "transport", None) or "sse"
            if transport != "sse":
                websocket_started = False
                try:
                    async for part in self._stream_websocket_raw_parts(
                        client,
                        _resolve_codex_websocket_url(resolved.base_url),
                        _build_websocket_headers(
                            headers,
                            api_key=api_key,
                            account_id=account_id,
                            request_id=session_id or _create_codex_request_id(),
                            codex_config=codex_config,
                        ),
                        body,
                        options,
                    ):
                        websocket_started = True
                        yield part
                    return
                except Exception:
                    if transport == "websocket" or websocket_started:
                        raise
            async for part in self._stream_sse_once(
                client, url, request_headers, body, options, debug_cb=_debug
            ):
                yield part
        except Exception as exc:
            yield provider_error_part(exc, source=self.api)
        finally:
            if owned_client is not None:
                with suppress(Exception):
                    await _close_owned_client(owned_client)

    async def _stream_sse_once(
        self,
        client,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        options,
        *,
        debug_cb=None,
    ) -> AsyncIterator[RawPart]:
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=body,
            timeout=get_timeout_seconds(options),
        ) as response:
            status_code = getattr(response, "status_code", 200)
            if status_code >= 400:
                error_text = await _parse_error_response(response)
                if callable(debug_cb):
                    debug_cb(
                        "response_error",
                        {
                            "status": status_code,
                            "headers": _response_headers(response),
                            "message": error_text,
                        },
                    )
                yield provider_error_part_from_raw(
                    error_text or f"Codex request failed with status {status_code}",
                    code=status_code,
                    source=self.api,
                )
                return
            async for part in process_responses_stream(
                _map_codex_events(_parse_sse_lines(response)),
                options=options,
                source=self.api,
            ):
                yield part

    async def _stream_websocket_raw_parts(
        self, client, url: str, headers: dict[str, str], body: dict[str, Any], options
    ) -> AsyncIterator[RawPart]:
        if hasattr(client, "connect_websocket"):
            session_id = getattr(options, "session_id", None)
            socket, release = await self._acquire_websocket(
                client, url, headers, session_id, get_timeout_seconds(options)
            )
            keep_connection = True
            try:
                await socket.send({"type": "response.create", **body})
                async for part in process_responses_stream(
                    _map_codex_events(_parse_websocket(socket.events())),
                    options=options,
                    source=self.api,
                ):
                    yield part
            except asyncio.CancelledError:
                keep_connection = False
                raise
            except Exception:
                keep_connection = False
                raise
            finally:
                await release(keep=keep_connection)
            return
        if not hasattr(client, "websocket_stream"):
            raise RuntimeError("WebSocket transport is not available in this runtime")
        events = client.websocket_stream(
            url,
            headers=headers,
            json={"type": "response.create", **body},
            timeout=get_timeout_seconds(options),
        )
        async for part in process_responses_stream(
            _map_codex_events(_objectify_events(events)),
            options=options,
            source=self.api,
        ):
            yield part

    async def _acquire_websocket(
        self, client, url: str, headers: dict[str, str], session_id: str | None, timeout
    ) -> tuple[Any, Any]:
        if not isinstance(session_id, str) or not session_id:
            socket = await client.connect_websocket(
                url, headers=headers, timeout=timeout
            )

            async def _release(*, keep: bool) -> None:
                await socket.close(1000, "done" if keep else "error")

            return socket, _release

        cached = self._websocket_session_cache.get(session_id)
        if cached is not None:
            if cached.idle_handle is not None:
                cached.idle_handle.cancel()
                cached.idle_handle = None
            if not cached.busy and not cached.closed:
                cached.busy = True

                async def _release_cached(*, keep: bool) -> None:
                    if not keep or cached.closed:
                        await cached.socket.close(1000, "done" if keep else "error")
                        cached.closed = True
                        self._websocket_session_cache.pop(session_id, None)
                        return
                    cached.busy = False
                    self._schedule_websocket_expiry(session_id, cached)

                return cached.socket, _release_cached
            if cached.busy or cached.closed:
                socket = await client.connect_websocket(
                    url, headers=headers, timeout=timeout
                )

                async def _release_busy(*, keep: bool) -> None:
                    await socket.close(1000, "done" if keep else "error")

                return socket, _release_busy

        socket = await client.connect_websocket(url, headers=headers, timeout=timeout)
        entry = _CachedWebSocketConnection(
            socket=socket, busy=True, closed=False, idle_handle=None
        )
        self._websocket_session_cache[session_id] = entry

        async def _release_new(*, keep: bool) -> None:
            if not keep or entry.closed:
                await entry.socket.close(1000, "done" if keep else "error")
                entry.closed = True
                self._websocket_session_cache.pop(session_id, None)
                return
            entry.busy = False
            self._schedule_websocket_expiry(session_id, entry)

        return entry.socket, _release_new

    def _schedule_websocket_expiry(
        self, session_id: str, entry: "_CachedWebSocketConnection"
    ) -> None:
        if entry.idle_handle is not None:
            entry.idle_handle.cancel()
        loop = asyncio.get_running_loop()

        def _expire() -> None:
            if entry.busy or entry.closed:
                return
            entry.closed = True
            self._websocket_session_cache.pop(session_id, None)
            asyncio.create_task(entry.socket.close(1000, "idle_timeout"))

        entry.idle_handle = loop.call_later(
            self._websocket_cache_ttl_ms / 1000.0, _expire
        )


def _codex_runtime_config(
    value: object | None,
) -> OpenAICodexRuntimeConfig:
    if isinstance(value, OpenAICodexRuntimeConfig):
        return value
    return OpenAICodexRuntimeConfig()


def _build_request_body(
    model,
    normalized: Mapping[str, Any],
    options,
    *,
    codex_config: OpenAICodexRuntimeConfig | None = None,
    capabilities: object | None = None,
    upstream_model_id: str | None = None,
) -> dict[str, Any]:
    codex_config = codex_config or OpenAICodexRuntimeConfig()
    input_items = convert_responses_messages(
        model,
        {
            **normalized,
            "system_prompt": None,
        },
        OpenAIResponsesConfig(),
        capabilities,
    )
    body: dict[str, Any] = {
        "model": upstream_model_id or model.id,
        "store": False,
        "stream": True,
        "input": input_items,
        "instructions": "",
        "text": {"verbosity": getattr(options, "text_verbosity", None) or "medium"},
        "include": ["reasoning.encrypted_content"],
    }
    system_prompt = normalized.get("system_prompt")
    if isinstance(system_prompt, str) and system_prompt.strip():
        body["instructions"] = sanitize_surrogates(system_prompt)
    if getattr(options, "temperature", None) is not None:
        body["temperature"] = getattr(options, "temperature")
    tools = convert_responses_tools(normalized.get("tools"))
    if isinstance(tools, list) and tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
        body["parallel_tool_calls"] = True
    session_id = getattr(options, "session_id", None)
    if isinstance(session_id, str) and session_id:
        body["prompt_cache_key"] = session_id
        prompt_cache_retention = codex_config.prompt_cache_retention
        if isinstance(prompt_cache_retention, str) and prompt_cache_retention:
            body["prompt_cache_retention"] = prompt_cache_retention
    reasoning = get_reasoning_effort(options)
    reasoning_summary = get_reasoning_summary(options)
    if reasoning is not None or reasoning_summary is not None:
        body["reasoning"] = {
            "effort": _clamp_reasoning_effort(model.id, reasoning or "medium"),
            "summary": reasoning_summary or "auto",
        }
    text_format = openai_responses_text_format(options)
    if text_format is not None:
        body["text"].update(text_format)
    return body


def _request_body_trace_summary(body: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "fields": sorted(str(key) for key in body),
    }
    model = body.get("model")
    if isinstance(model, str):
        summary["model"] = model
    for key in ("store", "stream", "parallel_tool_calls"):
        value = body.get(key)
        if isinstance(value, bool):
            summary[key] = value
    for key in ("temperature",):
        value = body.get(key)
        if isinstance(value, int | float):
            summary[key] = value
    instructions = body.get("instructions")
    if isinstance(instructions, str):
        summary["has_instructions"] = bool(instructions)
        summary["instruction_chars"] = len(instructions)
    input_items = body.get("input")
    if isinstance(input_items, list):
        summary["input_items"] = len(input_items)
    tools = body.get("tools")
    if isinstance(tools, list):
        summary["tool_count"] = len(tools)
    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, str):
        summary["tool_choice"] = tool_choice
    include = body.get("include")
    if isinstance(include, list):
        summary["include"] = [str(item) for item in include]
    text = body.get("text")
    if isinstance(text, Mapping):
        text_summary: dict[str, Any] = {
            "fields": sorted(str(key) for key in text),
        }
        verbosity = text.get("verbosity")
        if isinstance(verbosity, str):
            text_summary["verbosity"] = verbosity
        text_format = text.get("format")
        if isinstance(text_format, Mapping):
            format_type = text_format.get("type")
            text_summary["format_type"] = (
                format_type if isinstance(format_type, str) else "object"
            )
        summary["text"] = text_summary
    reasoning = body.get("reasoning")
    if isinstance(reasoning, Mapping):
        reasoning_summary: dict[str, Any] = {}
        effort = reasoning.get("effort")
        if isinstance(effort, str):
            reasoning_summary["effort"] = effort
        summary_value = reasoning.get("summary")
        if isinstance(summary_value, str):
            reasoning_summary["summary"] = summary_value
        summary["reasoning"] = reasoning_summary
    prompt_cache_key = body.get("prompt_cache_key")
    if isinstance(prompt_cache_key, str):
        summary["has_prompt_cache_key"] = bool(prompt_cache_key)
    prompt_cache_retention = body.get("prompt_cache_retention")
    if isinstance(prompt_cache_retention, str):
        summary["prompt_cache_retention"] = prompt_cache_retention
    return summary


def _clamp_reasoning_effort(model_id: str, effort: str) -> str:
    identifier = model_id.split("/")[-1]
    if (
        identifier.startswith("gpt-5.2")
        or identifier.startswith("gpt-5.3")
        or identifier.startswith("gpt-5.4")
    ) and effort == "minimal":
        return "low"
    if identifier == "gpt-5.1" and effort == "xhigh":
        return "high"
    if identifier == "gpt-5.1-codex-mini":
        return "high" if effort in {"high", "xhigh"} else "medium"
    return effort


def _resolve_codex_url(base_url: str | None) -> str:
    raw = (
        base_url.strip()
        if isinstance(base_url, str) and base_url.strip()
        else "https://chatgpt.com/backend-api"
    )
    normalized = raw.rstrip("/")
    if normalized.endswith("/codex/responses"):
        return normalized
    if normalized.endswith("/codex"):
        return f"{normalized}/responses"
    return f"{normalized}/codex/responses"


def _resolve_codex_websocket_url(base_url: str | None) -> str:
    url = _resolve_codex_url(base_url)
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    return url


def _extract_api_key(headers: dict[str, str]) -> str:
    auth = headers.get("Authorization") or headers.get("authorization")
    if isinstance(auth, str) and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    api_key = headers.get("x-api-key")
    if isinstance(api_key, str) and api_key:
        return api_key
    raise ValueError(
        "OpenAI Codex provider requires an API key (Authorization: Bearer or x-api-key)"
    )


def _extract_account_id(token: str) -> str:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid token")
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = json.loads(
            base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        )
        account_id = decoded.get("https://api.openai.com/auth", {}).get(
            "chatgpt_account_id"
        )
        if not isinstance(account_id, str) or not account_id:
            raise ValueError("missing account id")
        return account_id
    except Exception as exc:
        raise ValueError("Failed to extract accountId from token") from exc


def _resolve_account_id(
    headers: dict[str, str],
    *,
    api_key: str,
    auth_account_id: str | None = None,
) -> str:
    explicit_account_id = _header_value(headers, "chatgpt-account-id")
    if explicit_account_id:
        return explicit_account_id
    if auth_account_id:
        return auth_account_id
    return _extract_account_id(api_key)


def _header_value(headers: dict[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target and value:
            return value
    return None


def _build_sse_headers(
    init_headers: dict[str, str],
    *,
    api_key: str,
    account_id: str,
    session_id: str | None,
    codex_config: OpenAICodexRuntimeConfig | None = None,
) -> dict[str, str]:
    codex_config = codex_config or OpenAICodexRuntimeConfig()
    headers: dict[str, str] = {}
    for key, value in init_headers.items():
        if key.lower() in {"authorization", "x-api-key"}:
            continue
        headers[key] = value
    headers["Authorization"] = f"Bearer {api_key}"
    headers["chatgpt-account-id"] = account_id
    headers["originator"] = codex_config.originator or "loushang"
    headers["User-Agent"] = codex_config.user_agent or "loushang"
    headers["OpenAI-Beta"] = "responses=experimental"
    headers["accept"] = "text/event-stream"
    headers["content-type"] = "application/json"
    if isinstance(session_id, str) and session_id:
        headers["session_id"] = session_id
        if codex_config.include_client_request_id:
            headers["x-client-request-id"] = session_id
        if codex_config.include_conversation_id:
            headers["conversation_id"] = session_id
    return headers


def _build_websocket_headers(
    init_headers: dict[str, str],
    *,
    api_key: str,
    account_id: str,
    request_id: str,
    codex_config: OpenAICodexRuntimeConfig | None = None,
) -> dict[str, str]:
    codex_config = codex_config or OpenAICodexRuntimeConfig()
    headers: dict[str, str] = {}
    for key, value in init_headers.items():
        if key.lower() in {
            "authorization",
            "x-api-key",
            "accept",
            "content-type",
            "openai-beta",
        }:
            continue
        headers[key] = value
    headers["Authorization"] = f"Bearer {api_key}"
    headers["chatgpt-account-id"] = account_id
    headers["originator"] = codex_config.originator or "loushang"
    headers["User-Agent"] = codex_config.user_agent or "loushang"
    headers["OpenAI-Beta"] = "responses_websockets=2026-02-06"
    headers["x-client-request-id"] = request_id
    headers["session_id"] = request_id
    return headers


async def _parse_sse_lines(response) -> AsyncIterator[dict[str, Any]]:
    buffer: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if buffer:
                data_lines = [
                    entry[5:].strip() for entry in buffer if entry.startswith("data:")
                ]
                data = "\n".join(data_lines).strip()
                buffer.clear()
                if data and data != "[DONE]":
                    yield _objectify(json.loads(data))
            continue
        buffer.append(line)
    if buffer:
        data_lines = [
            entry[5:].strip() for entry in buffer if entry.startswith("data:")
        ]
        data = "\n".join(data_lines).strip()
        if data and data != "[DONE]":
            yield _objectify(json.loads(data))


async def _objectify_events(events: AsyncIterator[Any]) -> AsyncIterator[Any]:
    async for event in events:
        yield _objectify(event)


async def _parse_websocket(events: AsyncIterator[Any]) -> AsyncIterator[Any]:
    saw_completion = False
    async for event in events:
        event_obj = _objectify(event)
        event_type = getattr(event_obj, "type", None)
        if event_type in {"response.completed", "response.done", "response.incomplete"}:
            saw_completion = True
        yield event_obj
    if not saw_completion:
        raise RuntimeError("WebSocket stream closed before response.completed")


async def _map_codex_events(
    events: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    async for event in events:
        event_type = getattr(event, "type", None)
        if event_type in {"response.done", "response.completed", "response.incomplete"}:
            response_obj = getattr(event, "response", None)
            response: dict[str, Any] = {}
            if response_obj is not None:
                response = (
                    response_obj.__dict__.copy()
                    if hasattr(response_obj, "__dict__")
                    else dict(response_obj)
                )
            status = response.get("status")
            if status not in {
                "completed",
                "incomplete",
                "failed",
                "cancelled",
                "queued",
                "in_progress",
            }:
                response["status"] = None
            yield _objectify({"type": "response.completed", "response": response})
            return
        yield event


def _create_codex_request_id() -> str:
    return f"codex_{uuid4().hex}"


async def _response_text(response) -> str:
    text_method = getattr(response, "atext", None)
    if callable(text_method):
        value = await text_method()
        return value if isinstance(value, str) else str(value)
    read_method = getattr(response, "aread", None)
    if callable(read_method):
        payload = await read_method()
        if isinstance(payload, bytes):
            encoding = getattr(response, "encoding", None) or "utf-8"
            try:
                return payload.decode(encoding, errors="replace")
            except Exception:
                return payload.decode("utf-8", errors="replace")
        if isinstance(payload, str):
            return payload
    text_attr = getattr(response, "text", None)
    if isinstance(text_attr, str):
        return text_attr
    return ""


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        if _is_sensitive_header(key):
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def _is_sensitive_header(key: str) -> bool:
    compacted = "".join(char for char in key.lower() if char.isalnum())
    return compacted in {
        "authorization",
        "cookie",
        "proxyauthorization",
        "setcookie",
        "xaccesstoken",
        "xamzsecuritytoken",
        "xapikey",
        "xauthtoken",
        "xgoogapikey",
    }


def _response_headers(response) -> dict[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {}
    try:
        return dict(headers)
    except Exception:
        return {}


async def _parse_error_response(response) -> str:
    raw = await _response_text(response)
    message = raw or getattr(response, "status_text", "") or "Request failed"
    try:
        parsed = json.loads(raw)
    except Exception:
        return message
    if not isinstance(parsed, dict):
        return message
    detail = parsed.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    error = parsed.get("error")
    if not isinstance(error, dict):
        return message
    detail = error.get("message")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    code = error.get("code") or error.get("type")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return message


def _objectify(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _objectify(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_objectify(item) for item in value]
    return value


async def _close_owned_client(client: Any) -> None:
    close = getattr(client, "aclose", None)
    if not callable(close):
        close = getattr(client, "close", None)
    if not callable(close):
        return
    result = close()
    if isawaitable(result):
        await result


class _HttpxCodexClient:
    def __init__(self) -> None:
        try:
            import httpx  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "httpx is required for OpenAI Codex responses. Install via `pip install httpx`"
            ) from exc
        self._httpx = httpx
        self._client = httpx.AsyncClient()

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout=None,
    ):
        return self._client.stream(
            method, url, headers=headers, json=json, timeout=timeout
        )

    async def aclose(self) -> None:
        await self._client.aclose()


@dataclass
class _CachedWebSocketConnection:
    socket: Any
    busy: bool
    closed: bool
    idle_handle: Any | None = None
