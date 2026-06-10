from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal, cast

from loushang.channel.types import ChannelEndpoint, ChannelEnvelope
from loushang.work import WorkEvent, WorkOperation


def channel_envelope_to_json(envelope: ChannelEnvelope) -> dict[str, object]:
    return {
        "envelope_id": envelope.envelope_id,
        "kind": envelope.kind,
        "payload": _payload_to_json(envelope.payload),
        "source": _endpoint_to_json(envelope.source),
        "target": _endpoint_to_json(envelope.target),
        "created_at": envelope.created_at.isoformat() if envelope.created_at is not None else None,
        "metadata": _to_json_mapping(envelope.metadata),
    }


def channel_envelope_from_json(data: Mapping[str, object]) -> ChannelEnvelope:
    kind = cast(Literal["operation", "event"], data["kind"])
    if kind not in ("operation", "event"):
        raise ValueError("channel envelope kind must be 'operation' or 'event'")
    payload_data = _require_mapping(data["payload"], "payload")
    return ChannelEnvelope(
        envelope_id=str(data["envelope_id"]),
        kind=kind,
        payload=_payload_from_json(kind, payload_data),
        source=_endpoint_from_json(data.get("source")),
        target=_endpoint_from_json(data.get("target")),
        created_at=_datetime_from_json(data.get("created_at")),
        metadata=_mapping_or_empty(data.get("metadata")),
    )


def _payload_to_json(payload: WorkOperation | WorkEvent) -> dict[str, object]:
    if isinstance(payload, WorkOperation):
        return {
            "operation_id": payload.operation_id,
            "kind": payload.kind,
            "session_id": payload.session_id,
            "domain": payload.domain,
            "payload": _to_json_mapping(payload.payload),
            "source": _to_json_mapping(payload.source),
        }
    return {
        "event_id": payload.event_id,
        "kind": payload.kind,
        "run_id": payload.run_id,
        "session_id": payload.session_id,
        "domain": payload.domain,
        "operation_id": payload.operation_id,
        "sequence": payload.sequence,
        "created_at": payload.created_at.isoformat(),
        "delivery_hint": payload.delivery_hint,
        "payload": _to_json_mapping(payload.payload),
        "source_event_ref": payload.source_event_ref,
    }


def _payload_from_json(kind: Literal["operation", "event"], data: Mapping[str, object]) -> WorkOperation | WorkEvent:
    if kind == "operation":
        return WorkOperation(
            operation_id=str(data["operation_id"]),
            kind=str(data["kind"]),
            session_id=cast(str | None, data["session_id"]),
            domain=str(data["domain"]),
            payload=_mapping_or_empty(data.get("payload")),
            source=_mapping_or_empty(data.get("source")),
        )
    return WorkEvent(
        event_id=str(data["event_id"]),
        kind=str(data["kind"]),
        run_id=str(data["run_id"]),
        session_id=str(data["session_id"]),
        domain=str(data["domain"]),
        operation_id=str(data["operation_id"]),
        sequence=int(cast(int, data["sequence"])),
        created_at=_required_datetime_from_json(data["created_at"]),
        delivery_hint=cast(Literal["immediate", "coalesce", "final_only"], data["delivery_hint"]),
        payload=_mapping_or_empty(data.get("payload")),
        source_event_ref=cast(str | None, data.get("source_event_ref")),
    )


def _endpoint_to_json(endpoint: ChannelEndpoint | None) -> dict[str, object] | None:
    if endpoint is None:
        return None
    return {
        "endpoint_id": endpoint.endpoint_id,
        "kind": endpoint.kind,
        "session_id": endpoint.session_id,
        "metadata": _to_json_mapping(endpoint.metadata),
    }


def _endpoint_from_json(value: object) -> ChannelEndpoint | None:
    if value is None:
        return None
    data = _require_mapping(value, "endpoint")
    return ChannelEndpoint(
        endpoint_id=str(data["endpoint_id"]),
        kind=str(data["kind"]),
        session_id=cast(str | None, data.get("session_id")),
        metadata=_mapping_or_empty(data.get("metadata")),
    )


def _datetime_from_json(value: object) -> datetime | None:
    if value is None:
        return None
    return _required_datetime_from_json(value)


def _required_datetime_from_json(value: object) -> datetime:
    return datetime.fromisoformat(str(value))


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    if value is None:
        return {}
    return _require_mapping(value, "mapping")


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    return value


def _to_json_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _to_json_value(item) for key, item in value.items()}


def _to_json_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return _to_json_mapping(value)
    if isinstance(value, list | tuple):
        return [_to_json_value(item) for item in value]
    return repr(value)


__all__ = [
    "channel_envelope_from_json",
    "channel_envelope_to_json",
]
