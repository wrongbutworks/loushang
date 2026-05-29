from __future__ import annotations

import asyncio
import json
from typing import Any

from ..assembler import TextAssembler
from ..event_stream import create_assistant_message_event_stream
from ..raw_parts import RawDone, RawError, RawTextDelta
from ..registry import ApiProvider
from ..types import Context, Model, SimpleStreamOptions, StreamOptions


def create_httpx_provider(client_factory: Any | None = None) -> ApiProvider:
    def stream(model: Model, context: Context, options: StreamOptions | None = None):
        try:
            import httpx
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("httpx is not installed") from exc

        stream_obj, writer = create_assistant_message_event_stream()
        assembler = TextAssembler(writer=writer, model=model, context=context, provider_name=model.provider)

        async def run() -> None:
            assembler.start()
            client = client_factory() if client_factory is not None else httpx.AsyncClient()
            owns_client = client_factory is None
            stop_reason = "stop"
            try:
                if _is_cancelled(options):
                    assembler.fail(RawError(message="aborted"))
                    return
                headers = {
                    "x-api-key": options.api_key if options and options.api_key else "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    "accept": "text/event-stream",
                }
                body = {
                    "model": model.id,
                    "messages": context.messages,
                    "system": context.system_prompt,
                    "max_tokens": options.max_tokens if options and options.max_tokens else model.max_tokens,
                    "stream": True,
                }
                async with client.stream(
                    "POST",
                    f"{model.base_url.rstrip('/')}/v1/messages",
                    headers=headers,
                    json=body,
                    timeout=30.0,
                ) as response:
                    response.raise_for_status()
                    current_event: str | None = None
                    current_data: list[str] = []
                    response_id: str | None = None
                    usage_payload: dict[str, int] | None = None
                    async for line in response.aiter_lines():
                        if _is_cancelled(options):
                            assembler.fail(RawError(message="aborted", response_id=response_id, usage=usage_payload))
                            return
                        if not line:
                            if current_event and current_data:
                                payload = json.loads("\n".join(current_data))
                                if current_event == "message_start":
                                    response_id = _extract_response_id(payload)
                                if current_event == "content_block_delta":
                                    delta = payload.get("delta", {})
                                    if delta.get("type") == "text_delta":
                                        assembler.emit_text(RawTextDelta(text=delta.get("text", "")))
                                elif current_event == "message_delta":
                                    stop_reason = _map_stop_reason(payload.get("delta", {}).get("stop_reason"))
                                    usage_payload = _merge_usage(usage_payload, payload.get("usage"))
                                elif current_event == "message_stop":
                                    if _is_cancelled(options):
                                        assembler.fail(RawError(message="aborted", response_id=response_id, usage=usage_payload))
                                        return
                                    assembler.finish(
                                        RawDone(stop_reason=stop_reason, response_id=response_id, usage=usage_payload)
                                    )
                                    return
                            current_event = None
                            current_data = []
                            continue
                        if line.startswith("event:"):
                            current_event = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            current_data.append(line.split(":", 1)[1].lstrip())
                    assembler.finish(RawDone(stop_reason=stop_reason, response_id=response_id, usage=usage_payload))
            except Exception as exc:
                assembler.fail(RawError(message=str(exc)))
            finally:
                if owns_client:
                    await client.aclose()

        asyncio.create_task(run())
        return stream_obj

    def stream_simple(model: Model, context: Context, options: SimpleStreamOptions | None = None):
        return stream(model, context, options)

    return ApiProvider(api="anthropic-messages", stream=stream, stream_simple=stream_simple)


def _map_stop_reason(stop_reason: Any) -> str:
    if stop_reason in ("end_turn", "stop_sequence", "stop"):
        return "stop"
    if stop_reason == "max_tokens":
        return "length"
    if stop_reason == "tool_use":
        return "toolUse"
    if stop_reason == "aborted":
        return "aborted"
    return "error"


def _is_cancelled(options: StreamOptions | None) -> bool:
    return bool(getattr(options, "signal", None) and getattr(options.signal, "cancelled", False))


def _extract_response_id(payload: dict[str, Any]) -> str | None:
    message = payload.get("message")
    if isinstance(message, dict):
        value = message.get("id")
        if value:
            return str(value)
    value = payload.get("id")
    return str(value) if value else None


def _merge_usage(existing: dict[str, int] | None, incoming: Any) -> dict[str, int] | None:
    if incoming is None:
        return existing
    payload = {
        "input_tokens": _usage_value(incoming, "input_tokens"),
        "output_tokens": _usage_value(incoming, "output_tokens"),
        "cache_read_input_tokens": _usage_value(incoming, "cache_read_input_tokens"),
        "cache_creation_input_tokens": _usage_value(incoming, "cache_creation_input_tokens"),
    }
    if existing is None:
        return payload
    merged = existing.copy()
    for key, value in payload.items():
        merged[key] = max(int(merged.get(key, 0) or 0), int(value or 0))
    return merged


def _usage_value(incoming: Any, key: str) -> int:
    if isinstance(incoming, dict):
        return int(incoming.get(key, 0) or 0)
    return int(getattr(incoming, key, 0) or 0)
