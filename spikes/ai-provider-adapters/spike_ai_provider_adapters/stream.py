from __future__ import annotations

from .event_stream import AssistantMessageEventStream
from .registry import get_api_provider
from .types import AssistantMessage, Context, Model, SimpleStreamOptions, StreamOptions


def stream(model: Model, context: Context, options: StreamOptions | None = None) -> AssistantMessageEventStream:
    return get_api_provider(model.api).stream(model, context, options)


async def complete(model: Model, context: Context, options: StreamOptions | None = None) -> AssistantMessage:
    return await stream(model, context, options).result()


def stream_simple(
    model: Model,
    context: Context,
    options: SimpleStreamOptions | None = None,
) -> AssistantMessageEventStream:
    return get_api_provider(model.api).stream_simple(model, context, options)


async def complete_simple(
    model: Model,
    context: Context,
    options: SimpleStreamOptions | None = None,
) -> AssistantMessage:
    return await stream_simple(model, context, options).result()
