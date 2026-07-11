from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from loushang.ai.context import NormalizedContext
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.model import (
    Capabilities,
    EndpointRouting,
    EndpointTransport,
    Model,
    default_adapter_config,
)
from loushang.ai.options import CallOptions

ProviderContext = NormalizedContext
ProviderOptions = CallOptions | None
ProviderInvocationMode = Literal["complete", "stream"]


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    provider: str
    endpoint: str
    api: str
    base_url: str | None
    model: Model
    context: ProviderContext = field(
        default_factory=lambda: NormalizedContext(system_prompt=None)
    )
    options: ProviderOptions = None
    region: str | None = None
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

    def __post_init__(self) -> None:
        if not isinstance(self.model, Model):
            raise TypeError("ProviderRequest.model must be Model")
        model = self.model
        expected_provider = model.provider_id
        expected_endpoint = model.endpoint_id
        expected_api = model.api
        if not expected_provider or not expected_endpoint or not expected_api:
            raise ValueError(
                f"Model {model.id!r} is not bound to a concrete provider endpoint"
            )
        expected_facts = {
            "provider": expected_provider,
            "endpoint": expected_endpoint,
            "api": expected_api,
            "region": model.region,
            "capabilities": model.capabilities,
            "defaults": dict(model.defaults),
            "transport": model.transport,
            "routing": model.routing,
        }
        for field_name, expected in expected_facts.items():
            if getattr(self, field_name) != expected:
                raise ValueError(
                    f"ProviderRequest.{field_name} must match ProviderRequest.model"
                )

        model_base_url = model.base_url
        has_runtime_base_url = bool(model.base_url_env) or bool(
            isinstance(model_base_url, str)
            and re.search(r"\{[A-Z_][A-Z0-9_]*\}", model_base_url)
        )
        if not has_runtime_base_url and self.base_url != model_base_url:
            raise ValueError(
                "ProviderRequest.base_url must derive from ProviderRequest.model"
            )

        expected_adapter = model.adapter or default_adapter_config(expected_api)
        if self.adapter_config is None:
            object.__setattr__(self, "adapter_config", expected_adapter)
        elif self.adapter_config != expected_adapter:
            raise ValueError(
                "ProviderRequest.adapter_config must match ProviderRequest.model"
            )

        expected_upstream_id = model.upstream_id or model.id
        if self.upstream_model_id is None:
            object.__setattr__(self, "upstream_model_id", expected_upstream_id)
        elif self.upstream_model_id != expected_upstream_id:
            raise ValueError(
                "ProviderRequest.upstream_model_id must match ProviderRequest.model"
            )


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
