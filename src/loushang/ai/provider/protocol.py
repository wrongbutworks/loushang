from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

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

    def stream_raw(
        self,
        model: Model,
        context: ProviderContext,
        options: ProviderOptions,
        request: ResolvedRequest,
    ) -> AsyncIterator[Any]: ...


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
