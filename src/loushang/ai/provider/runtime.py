from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.provider.cancellation import is_signal_cancelled
from loushang.ai.provider.errors import provider_error_part
from loushang.ai.provider.resolution import ResolvedRequest

RawPartSource = Callable[[], AsyncIterator[RawPart] | Any]


def start_provider_runtime(
    raw_parts: RawPartSource,
    *,
    model,
    options,
    request: ResolvedRequest,
) -> AssistantMessageEventStream:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(
        stream=stream,
        api=request.api,
        provider=getattr(model, "provider_id", request.provider),
        model=getattr(model, "id", None) or request.upstream_model_id or "",
        pricing=getattr(model, "pricing", None),
    )

    async def _run() -> None:
        signal = getattr(options, "signal", None) if options is not None else None
        if is_signal_cancelled(signal):
            assembler.feed({"type": "aborted"})
            return
        try:
            source = raw_parts()
            if inspect.isawaitable(source):
                source = await source
            async for part in source:
                if is_signal_cancelled(signal):
                    assembler.feed({"type": "aborted"})
                    return
                assembler.feed(part)
        except Exception as error:
            assembler.feed(cast(RawPart, provider_error_part(error, source=request.api)))

    stream.attach_task(asyncio.create_task(_run()))
    return stream


__all__ = ["RawPartSource", "start_provider_runtime"]
