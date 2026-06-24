from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from loushang.ai.context import NormalizedContext
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.model import Model
from loushang.ai.options import CallOptions
from loushang.ai.provider.resolution import ResolvedRequest

ProviderContext = NormalizedContext
ProviderOptions = CallOptions | None


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    model: Model
    context: ProviderContext
    options: ProviderOptions
    resolved: ResolvedRequest


@runtime_checkable
class ApiProvider(Protocol):
    api: str

    def stream_raw(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[RawPart]: ...
