from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest


def test_channel_public_api_exposes_boundary_and_jsonl_surfaces() -> None:
    import loushang.channel as channel

    assert set(channel.__all__) == {
        "ChannelError",
        "ChannelDelivery",
        "ChannelDeliveryListener",
        "ChannelEndpoint",
        "ChannelEnvelope",
        "ChannelEnvelopeKind",
        "ChannelEventDelivery",
        "ChannelJsonProjectionError",
        "ChannelHost",
        "ChannelHostPort",
        "ChannelOperationAccepted",
        "ChannelOperationCancelRequest",
        "ChannelOperationCancelled",
        "ChannelOperationRequest",
        "ChannelPayload",
        "ChannelRpcFrame",
        "ChannelRpcFrameKind",
        "ChannelUnsubscribe",
        "ProductHostAction",
        "ProductHostActionType",
        "ProductHostAdapter",
        "ProductHostLifecycle",
        "ProductHostRuntime",
        "ProductHostStreams",
        "ProductHostState",
        "ProductHostStateReader",
        "ProductHostTaskTracker",
        "dispose_product_host",
        "JsonlCommand",
        "JsonlCommandErrorListener",
        "JsonlCommandHost",
        "JsonlCommandHostError",
        "JsonlCommandHostErrorKind",
        "JsonlCommandHostErrorReason",
        "JsonlCommandPort",
        "JsonlCommandHandler",
        "JsonlCommandRoute",
        "JsonlCommandRouter",
        "JsonlUnsupportedCommandHandler",
        "RemoteUiContext",
        "channel_envelope_from_json",
        "channel_envelope_to_json",
        "decode_rpc_jsonl_frame",
        "dispatch_product_host_action",
        "encode_rpc_jsonl_frame",
        "normalize_product_host_action",
        "project_channel_value",
        "rpc_jsonl_frame_from_json",
        "rpc_jsonl_frame_to_json",
        "flush_raw_stdout",
        "is_stdout_taken_over",
        "restore_stdout",
        "stdout_guard",
        "take_over_stdout",
        "write_raw_stdout",
    }


def test_channel_envelope_carries_work_operation_between_endpoints() -> None:
    from loushang.channel import ChannelEndpoint, ChannelEnvelope
    from loushang.work import WorkOperation

    operation = WorkOperation(
        operation_id="op-1",
        kind="SubmitCodingTurn",
        session_id="session-1",
        domain="coding",
        payload={"text": "inspect the repository"},
    )
    source = ChannelEndpoint(
        endpoint_id="client:tui",
        kind="tui",
        session_id="session-1",
        metadata={"transport": "in_process"},
    )
    target = ChannelEndpoint(endpoint_id="host:local", kind="host")

    envelope = ChannelEnvelope(
        envelope_id="env-1",
        kind="operation",
        payload=operation,
        source=source,
        target=target,
        metadata={"trace_id": "trace-1"},
    )

    assert envelope.kind == "operation"
    assert envelope.payload is operation
    assert envelope.source is source
    assert envelope.target is target
    assert envelope.metadata == {"trace_id": "trace-1"}
    assert envelope.created_at is None
    assert source.metadata == {"transport": "in_process"}
    assert not hasattr(envelope, "render")
    assert not hasattr(envelope, "execute")

    with pytest.raises(FrozenInstanceError):
        envelope.kind = "event"  # type: ignore[misc]


def test_channel_envelope_carries_work_event_for_client_delivery() -> None:
    from loushang.channel import ChannelEnvelope
    from loushang.work import WorkEvent

    created_at = datetime(2026, 6, 10, 12, 30, tzinfo=UTC)
    event = WorkEvent(
        event_id="event-1",
        kind="ContentDelta",
        run_id="run-1",
        session_id="session-1",
        domain="coding",
        operation_id="op-1",
        sequence=1,
        created_at=created_at,
        delivery_hint="coalesce",
        payload={"text": "hello"},
    )

    envelope = ChannelEnvelope(
        envelope_id="env-2",
        kind="event",
        payload=event,
        created_at=created_at,
    )

    assert envelope.kind == "event"
    assert envelope.payload is event
    assert envelope.created_at is created_at


def test_channel_envelope_carries_projected_runtime_event_for_client_delivery() -> None:
    from loushang.channel import ChannelEnvelope
    from loushang.harness.events import RuntimeEventView

    created_at = datetime(2026, 6, 10, 12, 30, tzinfo=UTC)
    event = RuntimeEventView(
        event_id="runtime-event-1",
        kind="agent.message_update",
        stream_id="session:session-1",
        sequence=4,
        occurred_at=created_at,
        event_type="assistant_delta",
        view="assistant_stream",
        payload={"type": "assistant_delta", "text": "hello"},
        delivery_hint="coalesce",
        session_id="session-1",
    )

    envelope = ChannelEnvelope(envelope_id="env-runtime-1", kind="event", payload=event)

    assert envelope.payload is event


def test_channel_envelope_rejects_mismatched_payload_kind() -> None:
    from loushang.channel import ChannelEnvelope
    from loushang.work import WorkOperation

    operation = WorkOperation(
        operation_id="op-1",
        kind="SubmitCodingTurn",
        session_id="session-1",
        domain="coding",
        payload={"text": "inspect the repository"},
    )

    with pytest.raises(TypeError, match="operation"):
        ChannelEnvelope(envelope_id="env-1", kind="event", payload=operation)


def test_channel_envelope_rejects_unknown_kind_at_runtime() -> None:
    from loushang.channel import ChannelEnvelope
    from loushang.work import WorkOperation

    operation = WorkOperation(
        operation_id="op-1",
        kind="SubmitCodingTurn",
        session_id="session-1",
        domain="coding",
        payload={"text": "inspect the repository"},
    )

    with pytest.raises(ValueError, match="kind"):
        ChannelEnvelope(
            envelope_id="env-1",
            kind="response",  # type: ignore[arg-type]
            payload=operation,
        )
