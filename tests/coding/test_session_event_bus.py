from __future__ import annotations

import asyncio


def test_session_event_bus_subscribes_unsubscribes_and_dispatches_sync_listeners() -> None:
    from loushang.coding.session.session_event_bus import SessionEventBus

    bus = SessionEventBus()
    seen: list[object] = []
    unsubscribe = bus.subscribe(seen.append)

    asyncio.run(bus.dispatch({"type": "queue_update", "steering": [], "follow_up": []}))
    unsubscribe()
    asyncio.run(bus.dispatch({"type": "queue_update", "steering": ["ignored"], "follow_up": []}))

    assert seen == [{"type": "queue_update", "steering": [], "follow_up": []}]


def test_session_event_bus_serializes_scheduled_dispatches() -> None:
    from loushang.coding.session.session_event_bus import SessionEventBus

    bus = SessionEventBus()
    started = asyncio.Event()
    release_first = asyncio.Event()
    seen: list[str] = []

    async def listener(event) -> None:
        seen.append(f"start:{event['id']}")
        if event["id"] == "first":
            started.set()
            await release_first.wait()
        seen.append(f"end:{event['id']}")

    bus.subscribe(listener)

    async def scenario() -> None:
        first = bus.schedule({"type": "custom", "id": "first"})
        await started.wait()
        second = bus.schedule({"type": "custom", "id": "second"})
        await asyncio.sleep(0)
        assert seen == ["start:first"]
        release_first.set()
        await first
        await second

    asyncio.run(scenario())

    assert seen == ["start:first", "end:first", "start:second", "end:second"]


def test_session_event_bus_dispatch_without_loop_rejects_async_listener() -> None:
    import pytest

    from loushang.coding.session.session_event_bus import SessionEventBus

    bus = SessionEventBus()

    async def listener(event) -> None:
        del event

    bus.subscribe(listener)

    with pytest.raises(RuntimeError, match="Async session listeners require a running event loop"):
        bus.dispatch_without_loop({"type": "queue_update", "steering": [], "follow_up": []})
