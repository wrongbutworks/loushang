from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from loushang.ai.context import NormalizedContext
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.model import Capabilities, EndpointRouting, EndpointTransport
from loushang.ai.options import CallOptions

ProviderContext = NormalizedContext
ProviderOptions = CallOptions | None
ProviderInvocationMode = Literal["complete", "stream"]


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    provider: str
    endpoint: str | None
    api: str
    base_url: str | None
    model: Any = None
    context: ProviderContext = field(
        default_factory=lambda: NormalizedContext(system_prompt=None)
    )
    options: ProviderOptions = None
    region: str | None = None
    candidate_base_urls: tuple[str, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    transport: EndpointTransport = field(default_factory=EndpointTransport)
    routing: EndpointRouting = field(default_factory=EndpointRouting)
    max_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | int | None = None
    upstream_model_id: str | None = None
    capabilities: Capabilities = field(default_factory=Capabilities)
    adapter_config: object | None = None
    mode: ProviderInvocationMode = "stream"


@runtime_checkable
class ApiProvider(Protocol):
    api: str

    def invoke_raw(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[RawPart]: ...


@runtime_checkable
class ProviderRequestValidator(Protocol):
    def validate_request(self, request: ProviderRequest) -> None: ...
