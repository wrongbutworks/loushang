from __future__ import annotations

import asyncio
from typing import Any

from ..assembler import TextAssembler
from ..event_stream import create_assistant_message_event_stream
from ..raw_parts import RawDone, RawError, RawTextDelta
from ..registry import ApiProvider
from ..types import Context, Model, SimpleStreamOptions, StreamOptions


def create_sdk_provider() -> ApiProvider:
    def stream(model: Model, context: Context, options: StreamOptions | None = None):
        try:
            from anthropic import AsyncAnthropic
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("anthropic is not installed") from exc

        stream_obj, writer = create_assistant_message_event_stream()
        assembler = TextAssembler(writer=writer, model=model, context=context, provider_name=model.provider)

        async def run() -> None:
            assembler.start()
            client = AsyncAnthropic(
                api_key=(options.api_key if options and options.api_key else None),
                base_url=model.base_url,
            )
            try:
                if _is_cancelled(options):
                    assembler.fail(RawError(message="aborted"))
                    return
                async with client.messages.stream(
                    model=model.id,
                    messages=context.messages,
                    system=context.system_prompt or None,
                    max_tokens=options.max_tokens if options and options.max_tokens else model.max_tokens,
                ) as response:
                    async for chunk in response.text_stream:
                        if _is_cancelled(options):
                            assembler.fail(RawError(message="aborted", response_id=getattr(response, "id", None)))
                            return
                        assembler.emit_text(RawTextDelta(text=chunk))
                    final_message = await response.get_final_message()
                    if _is_cancelled(options):
                        assembler.fail(RawError(message="aborted", response_id=getattr(final_message, "id", None)))
                        return
                    stop_reason = str(getattr(final_message, "stop_reason", "stop"))
                    assembler.finish(
                        RawDone(
                            stop_reason=_map_stop_reason(stop_reason),
                            response_id=getattr(final_message, "id", None),
                            usage=_usage_dict(getattr(final_message, "usage", None)),
                        )
                    )
            except Exception as exc:
                assembler.fail(RawError(message=str(exc)))

        asyncio.create_task(run())
        return stream_obj

    def stream_simple(model: Model, context: Context, options: SimpleStreamOptions | None = None):
        return stream(model, context, options)

    return ApiProvider(api="anthropic-messages", stream=stream, stream_simple=stream_simple)


def _map_stop_reason(stop_reason: str) -> str:
    if stop_reason in ("end_turn", "stop_sequence", "stop"):
        return "stop"
    if stop_reason == "max_tokens":
        return "length"
    if stop_reason == "tool_use":
        return "toolUse"
    return "error"


def _is_cancelled(options: StreamOptions | None) -> bool:
    return bool(getattr(options, "signal", None) and getattr(options.signal, "cancelled", False))


def _usage_dict(usage: Any | None) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_read_input_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        "cache_creation_input_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    }
