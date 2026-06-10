from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest


def test_channel_envelope_json_round_trips_work_operation() -> None:
    from loushang.channel import (
        ChannelEndpoint,
        ChannelEnvelope,
        channel_envelope_from_json,
        channel_envelope_to_json,
    )
    from loushang.work import WorkOperation

    created_at = datetime(2026, 6, 10, 13, 0, tzinfo=UTC)
    envelope = ChannelEnvelope(
        envelope_id="env-1",
        kind="operation",
        payload=WorkOperation(
            operation_id="op-1",
            kind="SubmitCodingTurn",
            session_id="session-1",
            domain="coding",
            payload={"text": "inspect", "paths": ("src", "tests")},
            source={"client": "tui"},
        ),
        source=ChannelEndpoint(endpoint_id="client:tui", kind="tui", session_id="session-1"),
        target=ChannelEndpoint(endpoint_id="host:local", kind="host", metadata={"pid": 123}),
        created_at=created_at,
        metadata={"trace_id": "trace-1"},
    )

    data = channel_envelope_to_json(envelope)

    assert json.loads(json.dumps(data, sort_keys=True)) == data
    assert data == {
        "envelope_id": "env-1",
        "kind": "operation",
        "payload": {
            "operation_id": "op-1",
            "kind": "SubmitCodingTurn",
            "session_id": "session-1",
            "domain": "coding",
            "payload": {"text": "inspect", "paths": ["src", "tests"]},
            "source": {"client": "tui"},
        },
        "source": {
            "endpoint_id": "client:tui",
            "kind": "tui",
            "session_id": "session-1",
            "metadata": {},
        },
        "target": {
            "endpoint_id": "host:local",
            "kind": "host",
            "session_id": None,
            "metadata": {"pid": 123},
        },
        "created_at": "2026-06-10T13:00:00+00:00",
        "metadata": {"trace_id": "trace-1"},
    }

    decoded = channel_envelope_from_json(data)

    assert decoded == ChannelEnvelope(
        envelope_id="env-1",
        kind="operation",
        payload=WorkOperation(
            operation_id="op-1",
            kind="SubmitCodingTurn",
            session_id="session-1",
            domain="coding",
            payload={"text": "inspect", "paths": ["src", "tests"]},
            source={"client": "tui"},
        ),
        source=ChannelEndpoint(endpoint_id="client:tui", kind="tui", session_id="session-1"),
        target=ChannelEndpoint(endpoint_id="host:local", kind="host", metadata={"pid": 123}),
        created_at=created_at,
        metadata={"trace_id": "trace-1"},
    )


def test_channel_envelope_json_round_trips_work_event() -> None:
    from loushang.channel import (
        ChannelEnvelope,
        channel_envelope_from_json,
        channel_envelope_to_json,
    )
    from loushang.work import WorkEvent

    event_created_at = datetime(2026, 6, 10, 13, 1, tzinfo=UTC)
    envelope_created_at = datetime(2026, 6, 10, 13, 2, tzinfo=UTC)
    envelope = ChannelEnvelope(
        envelope_id="env-2",
        kind="event",
        payload=WorkEvent(
            event_id="event-1",
            kind="ContentDelta",
            run_id="run-1",
            session_id="session-1",
            domain="coding",
            operation_id="op-1",
            sequence=7,
            created_at=event_created_at,
            delivery_hint="coalesce",
            payload={"text": "hello"},
            source_event_ref="agent:event:1",
        ),
        created_at=envelope_created_at,
    )

    data = channel_envelope_to_json(envelope)

    assert data["payload"] == {
        "event_id": "event-1",
        "kind": "ContentDelta",
        "run_id": "run-1",
        "session_id": "session-1",
        "domain": "coding",
        "operation_id": "op-1",
        "sequence": 7,
        "created_at": "2026-06-10T13:01:00+00:00",
        "delivery_hint": "coalesce",
        "payload": {"text": "hello"},
        "source_event_ref": "agent:event:1",
    }
    assert channel_envelope_from_json(data) == envelope


def test_channel_envelope_json_decode_rejects_unknown_kind() -> None:
    from loushang.channel import channel_envelope_from_json

    with pytest.raises(ValueError, match="kind"):
        channel_envelope_from_json(
            {
                "envelope_id": "env-1",
                "kind": "response",
                "payload": {},
                "source": None,
                "target": None,
                "created_at": None,
                "metadata": {},
            }
        )
