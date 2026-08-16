from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias, cast, runtime_checkable
from uuid import uuid4

from loushang.ai.json_codec import deserialize_usage, serialize_usage
from loushang.ai.types import AssistantMessage, StopReason, Usage
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
PREPARED_MODEL_CALL_OUTCOME_SCHEMA_VERSION = 1
PreparedModelCallDisposition: TypeAlias = Literal[
    "completed",
    "failed",
    "cancelled",
]


@dataclass(frozen=True, slots=True)
class PreparedModelCallOutcome:
    """Content-free terminal result for one logical Provider invocation."""

    invocation_id: str
    disposition: PreparedModelCallDisposition
    stop_reason: StopReason
    usage: Usage
    error_info: Mapping[str, FrozenJSONValue] | None = field(
        default=None,
        repr=False,
    )
    schema_version: int = PREPARED_MODEL_CALL_OUTCOME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.invocation_id, str) or not self.invocation_id:
            raise ValueError(
                "PreparedModelCallOutcome.invocation_id must be non-empty"
            )
        if self.schema_version != PREPARED_MODEL_CALL_OUTCOME_SCHEMA_VERSION:
            raise ValueError(
                "unsupported PreparedModelCallOutcome schema version: "
                f"{self.schema_version}"
            )
        expected_disposition: PreparedModelCallDisposition
        if self.stop_reason == "error":
            expected_disposition = "failed"
        elif self.stop_reason == "aborted":
            expected_disposition = "cancelled"
        elif self.stop_reason in {"stop", "length", "toolUse"}:
            expected_disposition = "completed"
        else:
            raise ValueError(
                f"unsupported PreparedModelCallOutcome stop reason: {self.stop_reason}"
            )
        if self.disposition != expected_disposition:
            raise ValueError(
                "PreparedModelCallOutcome disposition does not match stop reason"
            )
        if not isinstance(self.usage, Usage):
            raise TypeError("PreparedModelCallOutcome.usage must be Usage")
        for name in ("input", "output", "cache_read", "cache_write", "total_tokens"):
            value = getattr(self.usage, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(
                    f"PreparedModelCallOutcome.usage.{name} must be non-negative"
                )
        canonical_usage = deserialize_usage(serialize_usage(self.usage))
        if canonical_usage != self.usage:
            raise ValueError(
                "PreparedModelCallOutcome.usage cost must be finite and non-negative"
            )
        object.__setattr__(self, "usage", canonical_usage)
        if self.error_info is None:
            if self.disposition == "failed":
                raise ValueError("failed PreparedModelCallOutcome requires error info")
            return
        if self.disposition != "failed":
            raise ValueError(
                "non-failed PreparedModelCallOutcome cannot contain error info"
            )
        projected = require_json_mapping(
            self.error_info,
            name="prepared model call outcome error info",
        )
        object.__setattr__(self, "error_info", _freeze_json(projected))

    @classmethod
    def from_assistant_message(
        cls,
        invocation_id: str,
        message: AssistantMessage,
    ) -> PreparedModelCallOutcome:
        if not isinstance(message, AssistantMessage):
            raise TypeError("PreparedModelCallOutcome requires AssistantMessage")
        disposition: PreparedModelCallDisposition
        if message.stop_reason == "error":
            disposition = "failed"
        elif message.stop_reason == "aborted":
            disposition = "cancelled"
        else:
            disposition = "completed"
        return cls(
            invocation_id=invocation_id,
            disposition=disposition,
            stop_reason=message.stop_reason,
            usage=message.usage,
            error_info=cast(
                Mapping[str, FrozenJSONValue] | None,
                message.error_info,
            ),
        )


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
        """Return a fresh transport object without reordering adapter mappings."""

        digest = "sha256:" + hashlib.sha256(
            self.canonical_payload.encode("utf-8")
        ).hexdigest()
        if digest != self.payload_hash:
            raise RuntimeError("prepared model request payload hash mismatch")
        return _project_payload(self.payload)

    def model_visible_headers_for_transport(self) -> dict[str, str]:
        return dict(self.model_visible_headers)


@runtime_checkable
class PreparedRequestCommitter(Protocol):
    async def commit_prepared_request(self, request: PreparedModelRequest) -> None: ...


@runtime_checkable
class PreparedModelCallOutcomeRecorder(Protocol):
    async def record_model_call_outcome(
        self,
        outcome: PreparedModelCallOutcome,
    ) -> None: ...


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
    _raise_if_transport_cancelled()
    async for part in adapter.invoke_prepared_raw(request, prepared):
        yield part


def _raise_if_transport_cancelled() -> None:
    """Keep a committer from consuming caller cancellation before transport."""

    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError


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
    "PREPARED_MODEL_CALL_OUTCOME_SCHEMA_VERSION",
    "PreparedModelCallDisposition",
    "PreparedModelCallOutcome",
    "PreparedModelCallOutcomeRecorder",
    "PreparedModelRequest",
    "PreparedRequestAdapter",
    "PreparedRequestCommitter",
    "commit_prepared_request",
    "invoke_prepared_request",
]
