from __future__ import annotations

from typing import Protocol, runtime_checkable

from loushang.ai.context import NormalizedContext
from loushang.ai.event_stream import AssistantMessageEventStream
from loushang.ai.model import Model
from loushang.ai.options import CallOptions
from loushang.ai.provider.resolution import ResolvedRequest

ProviderContext = NormalizedContext
ProviderOptions = CallOptions | None


@runtime_checkable
class ApiProvider(Protocol):
    api: str

    async def stream(
        self,
        model: Model,
        context: ProviderContext,
        options: ProviderOptions,
    ) -> AssistantMessageEventStream: ...

    async def stream_simple(
        self,
        model: Model,
        context: ProviderContext,
        options: ProviderOptions,
    ) -> AssistantMessageEventStream: ...


@runtime_checkable
class RequestAwareApiProvider(Protocol):
    api: str

    async def stream(
        self,
        model: Model,
        context: ProviderContext,
        options: ProviderOptions,
        request: ResolvedRequest | None = None,
    ) -> AssistantMessageEventStream: ...

    async def stream_simple(
        self,
        model: Model,
        context: ProviderContext,
        options: ProviderOptions,
        request: ResolvedRequest | None = None,
    ) -> AssistantMessageEventStream: ...
