from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from loushang.ai.event_stream import AssistantMessageEventStream
from loushang.ai.model import Model
from loushang.ai.options import ModelCallOptions
from loushang.ai.types import Context

ProviderContext = Context | dict[str, Any]
ProviderOptions = ModelCallOptions | None


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
