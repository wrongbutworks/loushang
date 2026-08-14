from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, TypeAlias, cast, runtime_checkable
from uuid import uuid4

from loushang.foundation.json import JSONValue, require_json_mapping

if TYPE_CHECKING:
    from loushang.ai.event_stream.raw_parts import RawPart
    from loushang.ai.provider.protocol import ProviderRequest

FrozenJSONPrimitive: TypeAlias = str | int | float | bool | None
FrozenJSONValue: TypeAlias = (
    FrozenJSONPrimitive
    | tuple["FrozenJSONValue", ...]
    | Mapping[str, "FrozenJSONValue"]
)

PREPARED_MODEL_REQUEST_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class PreparedModelRequest:
    """Immutable, provider-facing model payload committed before transport."""

    invocation_id: str
    attempt: int
    provider_id: str
    endpoint_id: str
    api: str
    model_id: str
    mode: str
    payload: Mapping[str, FrozenJSONValue] = field(repr=False)
    model_visible_headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    schema_version: int = PREPARED_MODEL_REQUEST_SCHEMA_VERSION
    canonical_payload: str = field(init=False, repr=False)
    payload_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "invocation_id",
            "provider_id",
            "endpoint_id",
            "api",
            "model_id",
            "mode",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"PreparedModelRequest.{name} must be non-empty")
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt < 1
        ):
            raise ValueError("PreparedModelRequest.attempt must be a positive integer")
        if self.schema_version != PREPARED_MODEL_REQUEST_SCHEMA_VERSION:
            raise ValueError(
                "unsupported PreparedModelRequest schema version: "
                f"{self.schema_version}"
            )

        projected = _project_payload(self.payload)
        model_visible_headers = _project_model_visible_headers(
            self.model_visible_headers
        )
        canonical_payload = json.dumps(
            {
                "model_visible_headers": model_visible_headers,
                "payload": projected,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        object.__setattr__(self, "payload", _freeze_json(projected))
        object.__setattr__(
            self,
            "model_visible_headers",
            MappingProxyType(model_visible_headers),
        )
        object.__setattr__(self, "canonical_payload", canonical_payload)
        object.__setattr__(
            self,
            "payload_hash",
            "sha256:"
            + hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest(),
        )

    @classmethod
    def from_provider_request(
        cls,
        request: ProviderRequest,
        *,
        payload: Mapping[str, object],
        model_visible_headers: Mapping[str, str] | None = None,
    ) -> PreparedModelRequest:
        model = request.model
        return cls(
            invocation_id=request.invocation_id or uuid4().hex,
            attempt=request.attempt,
            provider_id=model.provider_id,
            endpoint_id=model.endpoint_id,
            api=model.api or "",
            model_id=model.id,
            mode=request.mode,
            payload=cast(Mapping[str, FrozenJSONValue], payload),
            model_visible_headers=model_visible_headers or {},
        )

    def payload_for_transport(self) -> dict[str, JSONValue]:
        """Return a fresh transport object derived only from the frozen bytes."""

        digest = "sha256:" + hashlib.sha256(
            self.canonical_payload.encode("utf-8")
        ).hexdigest()
        if digest != self.payload_hash:
            raise RuntimeError("prepared model request payload hash mismatch")
        decoded = json.loads(self.canonical_payload)
        envelope = require_json_mapping(decoded, name="prepared model request")
        return require_json_mapping(
            envelope["payload"],
            name="prepared model request payload",
        )

    def model_visible_headers_for_transport(self) -> dict[str, str]:
        return dict(self.model_visible_headers)


@runtime_checkable
class PreparedRequestCommitter(Protocol):
    async def commit_prepared_request(self, request: PreparedModelRequest) -> None: ...


@runtime_checkable
class PreparedRequestAdapter(Protocol):
    api: str

    def prepare_request(self, request: ProviderRequest) -> PreparedModelRequest: ...

    def invoke_prepared_raw(
        self,
        request: ProviderRequest,
        prepared: PreparedModelRequest,
    ) -> AsyncIterator[RawPart]: ...

    def invoke_raw(self, request: ProviderRequest) -> AsyncIterator[RawPart]: ...


async def commit_prepared_request(
    request: PreparedModelRequest,
    committer: PreparedRequestCommitter | None,
) -> None:
    if committer is not None:
        await committer.commit_prepared_request(request)


async def invoke_prepared_request(
    adapter: PreparedRequestAdapter,
    request: ProviderRequest,
) -> AsyncIterator[RawPart]:
    prepared = adapter.prepare_request(request)
    committer = (
        request.options.prepared_request_committer
        if request.options is not None
        else None
    )
    await commit_prepared_request(prepared, committer)
    async for part in adapter.invoke_prepared_raw(request, prepared):
        yield part


def _project_payload(payload: Mapping[str, FrozenJSONValue]) -> dict[str, JSONValue]:
    projected = _thaw_json(payload)
    return require_json_mapping(projected, name="prepared model request payload")


def _project_model_visible_headers(headers: Mapping[str, str]) -> dict[str, str]:
    projected: dict[str, str] = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not name:
            raise ValueError("model-visible header names must be non-empty strings")
        if not isinstance(value, str) or not value:
            raise ValueError("model-visible header values must be non-empty strings")
        if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            raise ValueError("model-visible headers must not contain CR or LF")
        projected[name] = value
    return projected


def _freeze_json(value: JSONValue) -> FrozenJSONValue:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> JSONValue:
    if isinstance(value, Mapping):
        projected: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("prepared model request payload keys must be strings")
            projected[key] = _thaw_json(item)
        return projected
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_thaw_json(item) for item in value]
    return cast(JSONValue, value)


__all__ = [
    "PREPARED_MODEL_REQUEST_SCHEMA_VERSION",
    "PreparedModelRequest",
    "PreparedRequestAdapter",
    "PreparedRequestCommitter",
    "commit_prepared_request",
    "invoke_prepared_request",
]
