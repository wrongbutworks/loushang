from __future__ import annotations

import asyncio

from ..assembler import TextAssembler
from ..event_stream import create_assistant_message_event_stream
from ..raw_parts import RawDone, RawTextDelta
from ..registry import ApiProvider
from ..types import Context, Model, SimpleStreamOptions, StreamOptions


def _run_faux(model: Model, context: Context, provider_name: str, text: str):
    stream, writer = create_assistant_message_event_stream()
    assembler = TextAssembler(writer=writer, model=model, context=context, provider_name=provider_name)

    async def run() -> None:
        assembler.start()
        for chunk in text.split():
            assembler.emit_text(RawTextDelta(text=chunk + " "))
            await asyncio.sleep(0)
        assembler.finish(RawDone())

    asyncio.create_task(run())
    return stream


def create_faux_provider(api: str = "anthropic-messages") -> ApiProvider:
    def stream(model: Model, context: Context, options: StreamOptions | None = None):
        return _run_faux(model, context, "faux", "mock hello from faux provider")

    def stream_simple(model: Model, context: Context, options: SimpleStreamOptions | None = None):
        return _run_faux(model, context, "faux", "mock hello from faux provider")

    return ApiProvider(api=api, stream=stream, stream_simple=stream_simple)

