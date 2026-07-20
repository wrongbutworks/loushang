from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from io import StringIO

from loushang.channel import (
    ChannelHost,
    ChannelOperationCancelRequest,
    ChannelOperationRequest,
    encode_rpc_jsonl_frame,
)
from loushang.channel.types import ChannelEnvelope
from loushang.coding.mode.channel_mode import (
    CodingChannelOperationPort,
    run_channel_mode,
)
from loushang.harness.events import RuntimeEvent, RuntimeEventView
from loushang.work import WorkOperation


class _FakeSession:
    def __init__(self) -> None:
        self.session_id = "session-1"
        self.listeners = []
        self.prompt_calls: list[dict[str, object]] = []
        self.abort_calls = 0
        self.idle_waits = 0
        self.release = asyncio.Event()
        self.unsubscribe_calls = 0

    @property
    def session_control(self) -> "_FakeSession":
        return self

    def subscribe_runtime_events(self, listener):
        self.listeners.append(listener)

        def unsubscribe() -> None:
            self.unsubscribe_calls += 1
            if listener in self.listeners:
                self.listeners.remove(listener)

        return unsubscribe

    async def prompt(
        self,
        text: str,
        *,
        streaming_behavior: str | None = None,
        source: str | None = None,
    ) -> None:
        self.prompt_calls.append(
            {
                "text": text,
                "streaming_behavior": streaming_behavior,
                "source": source,
            }
        )
        await self.release.wait()

    def abort(self) -> None:
        self.abort_calls += 1
        self.release.set()

    async def wait_for_idle(self) -> None:
        self.idle_waits += 1

    def emit(self, event: RuntimeEvent[object]) -> None:
        for listener in tuple(self.listeners):
            listener(event)


def test_coding_channel_port_accepts_standard_turn_and_projects_runtime_event() -> None:
    async def scenario() -> None:
        session = _FakeSession()
        port = CodingChannelOperationPort(session=session)
        deliveries = []
        unsubscribe = port.subscribe_deliveries(deliveries.append)

        result = await port.accept_operation(_request())
        await asyncio.sleep(0)
        session.emit(_queue_runtime_event())

        assert result.operation_id == "operation-1"
        assert session.prompt_calls == [
            {
                "text": "inspect the repository",
                "streaming_behavior": None,
                "source": "channel",
            }
        ]
        assert len(deliveries) == 1
        delivery = deliveries[0]
        assert isinstance(delivery.envelope.payload, RuntimeEventView)
        assert delivery.envelope.payload.correlation_id == "operation-1"
        assert delivery.envelope.payload.payload["type"] == "queue_update"

        session.release.set()
        await asyncio.sleep(0)
        assert session.idle_waits == 1
        unsubscribe()
        port.close()

    asyncio.run(scenario())


def test_coding_channel_port_rejects_non_standard_operation_before_prompting() -> None:
    async def scenario() -> None:
        session = _FakeSession()
        port = CodingChannelOperationPort(session=session)
        request = _request(kind="SetCodingModel")

        result = await port.accept_operation(request)

        assert result.code == "unsupported_operation"
        assert session.prompt_calls == []
        port.close()

    asyncio.run(scenario())


def test_coding_channel_port_cancels_active_operation_through_session_abort() -> None:
    async def scenario() -> None:
        session = _FakeSession()
        port = CodingChannelOperationPort(session=session)
        await port.accept_operation(_request())
        await asyncio.sleep(0)

        result = await port.cancel_operation(
            ChannelOperationCancelRequest(
                request_id="cancel-1",
                operation_id="operation-1",
            )
        )
        await asyncio.sleep(0)

        assert result.operation_id == "operation-1"
        assert session.abort_calls == 1
        port.close()

    asyncio.run(scenario())


def test_channel_host_correlates_coding_runtime_views_to_standard_request() -> None:
    async def scenario() -> None:
        session = _FakeSession()
        port = CodingChannelOperationPort(session=session)
        stdout = StringIO()
        host = ChannelHost(port=port, stdin=StringIO(), stdout=stdout)
        unsubscribe = port.subscribe_deliveries(host.deliver)

        await host.handle_line(encode_rpc_jsonl_frame(_request()))
        await asyncio.sleep(0)
        session.emit(_queue_runtime_event())

        frames = [
            json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()
        ]
        assert frames[0]["frame_type"] == "operation_accepted"
        assert frames[1]["frame_type"] == "event"
        assert frames[1]["request_id"] == "request-1"
        assert frames[1]["envelope"]["payload"]["correlation_id"] == "operation-1"

        session.release.set()
        await asyncio.sleep(0)
        unsubscribe()
        port.close()

    asyncio.run(scenario())


def test_run_channel_mode_uses_active_session_and_releases_subscription() -> None:
    class _Runtime:
        def __init__(self, session: _FakeSession) -> None:
            self._session = session

        def get_current_session(self) -> _FakeSession:
            return self._session

    async def scenario() -> None:
        session = _FakeSession()
        stdout = StringIO()

        exit_code = await run_channel_mode(
            runtime=_Runtime(session),
            stdin=StringIO(encode_rpc_jsonl_frame(_request()) + "\n"),
            stdout=stdout,
        )

        frames = [
            json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()
        ]
        assert exit_code == 0
        assert frames == [
            {
                "frame_type": "operation_accepted",
                "operation_id": "operation-1",
                "request_id": "request-1",
                "run_id": None,
            }
        ]
        assert session.unsubscribe_calls == 1

    asyncio.run(scenario())


def _request(
    *,
    kind: str = "SubmitCodingTurn",
) -> ChannelOperationRequest:
    return ChannelOperationRequest(
        request_id="request-1",
        envelope=ChannelEnvelope(
            envelope_id="envelope-1",
            kind="operation",
            payload=WorkOperation(
                operation_id="operation-1",
                kind=kind,
                session_id="session-1",
                domain="coding",
                payload={"text": "inspect the repository"},
            ),
        ),
    )


def _queue_runtime_event() -> RuntimeEvent[object]:
    return RuntimeEvent(
        event_id="event-1",
        kind="queue.changed",
        stream_id="session:session-1",
        sequence=1,
        occurred_at=datetime(2026, 7, 19, tzinfo=UTC),
        session_id="session-1",
        payload={"type": "queue_update", "steering": [], "follow_up": []},
    )
