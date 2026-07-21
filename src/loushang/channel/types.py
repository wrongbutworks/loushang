from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, TypeAlias

from loushang.work import WorkEvent, WorkOperation

if TYPE_CHECKING:
    from loushang.harness.events.projection import RuntimeEventView

ChannelEnvelopeKind: TypeAlias = Literal["operation", "event"]
ChannelPayload: TypeAlias = WorkOperation | WorkEvent | object


@dataclass(frozen=True)
class ChannelEndpoint:
    endpoint_id: str
    kind: str
    session_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelEnvelope:
    envelope_id: str
    kind: ChannelEnvelopeKind
    payload: ChannelPayload
    source: ChannelEndpoint | None = None
    target: ChannelEndpoint | None = None
    created_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in ("operation", "event"):
            raise ValueError("channel envelope kind must be 'operation' or 'event'")
        if self.kind == "operation" and not isinstance(self.payload, WorkOperation):
            actual = _payload_name(self.payload)
            raise TypeError(
                f"operation channel envelopes cannot carry {actual} payload"
            )
        if self.kind == "event" and not _is_event_payload(self.payload):
            actual = _payload_name(self.payload)
            raise TypeError(f"event channel envelopes cannot carry {actual} payload")


def _payload_name(payload: object) -> str:
    if isinstance(payload, WorkOperation):
        return "operation"
    if isinstance(payload, WorkEvent):
        return "event"
    if isinstance(payload, RuntimeEventView):
        return "runtime event view"
    return type(payload).__name__


def _is_event_payload(payload: object) -> bool:
    if isinstance(payload, WorkEvent):
        return True
    # Keep importing the optional Agent event view lazy so importing Channel
    # never initializes Agent/AI provider modules.
    from loushang.harness.events.projection import RuntimeEventView

    return isinstance(payload, RuntimeEventView)


__all__ = [
    "ChannelEndpoint",
    "ChannelEnvelope",
    "ChannelEnvelopeKind",
    "ChannelPayload",
]
