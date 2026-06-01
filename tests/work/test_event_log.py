from __future__ import annotations

import asyncio
from datetime import UTC, datetime


def _entry(
    entry_id: str,
    *,
    entry_type: str = "event",
    operation_id: str = "op-1",
    event_id: str | None = "event-1",
    run_id: str = "run-1",
    session_id: str = "session-1",
    sequence: int = 1,
) -> object:
    from loushang.work import EventLogEntry

    return EventLogEntry(
        entry_id=entry_id,
        entry_type=entry_type,
        operation_id=operation_id,
        event_id=event_id,
        run_id=run_id,
        session_id=session_id,
        sequence=sequence,
        payload={"kind": "WorkRunStarted"},
        created_at=datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
    )


def test_in_memory_event_log_appends_and_queries_by_run_and_session() -> None:
    from loushang.work import InMemoryEventLogBackend

    backend = InMemoryEventLogBackend()
    first = _entry("entry-1", run_id="run-1", session_id="session-1", sequence=1)
    second = _entry("entry-2", run_id="run-2", session_id="session-1", sequence=1)
    third = _entry("entry-3", run_id="run-1", session_id="session-2", sequence=2)

    first_position = backend.append(first)
    second_position = backend.append(second)
    third_position = backend.append(third)

    assert first_position.offset == 1
    assert second_position.offset == 2
    assert third_position.offset == 3
    assert backend.query(run_id="run-1") == [first, third]
    assert backend.query(session_id="session-1") == [first, second]
    assert backend.query(run_id="run-1", session_id="session-2") == [third]
    assert backend.query(run_id="run-1", after=first_position) == [third]
    assert backend.query(limit=2) == [first, second]


def test_in_memory_event_log_subscribe_replays_existing_then_streams_later_entries() -> None:
    from loushang.work import InMemoryEventLogBackend

    async def scenario() -> None:
        backend = InMemoryEventLogBackend()
        existing = _entry("entry-1", run_id="run-1", sequence=1)
        ignored = _entry("entry-ignored", run_id="run-2", sequence=1)
        later = _entry("entry-2", run_id="run-1", sequence=2)
        backend.append(existing)

        stream = backend.subscribe(run_id="run-1")
        assert await asyncio.wait_for(anext(stream), timeout=0.1) == existing

        next_entry = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        backend.append(ignored)
        backend.append(later)

        assert await asyncio.wait_for(next_entry, timeout=0.1) == later
        await stream.aclose()

    asyncio.run(scenario())
