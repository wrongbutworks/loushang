from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Mapping, Protocol


@dataclass(frozen=True, order=True)
class EventPosition:
    offset: int


@dataclass(frozen=True)
class EventLogEntry:
    entry_id: str
    entry_type: Literal["operation", "event"]
    operation_id: str
    event_id: str | None
    run_id: str
    session_id: str
    sequence: int
    payload: Mapping[str, object]
    created_at: datetime


class EventLogBackend(Protocol):
    def append(self, entry: EventLogEntry) -> EventPosition: ...

    def query(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        after: EventPosition | None = None,
        limit: int | None = None,
    ) -> list[EventLogEntry]: ...

    def subscribe(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        after: EventPosition | None = None,
    ) -> AsyncIterator[EventLogEntry]: ...


@dataclass
class _Subscriber:
    run_id: str | None
    session_id: str | None
    queue: asyncio.Queue[EventLogEntry] = field(default_factory=asyncio.Queue)


class InMemoryEventLogBackend:
    def __init__(self) -> None:
        self._entries: list[tuple[EventPosition, EventLogEntry]] = []
        self._subscribers: list[_Subscriber] = []

    def append(self, entry: EventLogEntry) -> EventPosition:
        position = EventPosition(offset=len(self._entries) + 1)
        self._entries.append((position, entry))
        for subscriber in list(self._subscribers):
            if _matches(entry, run_id=subscriber.run_id, session_id=subscriber.session_id):
                subscriber.queue.put_nowait(entry)
        return position

    def query(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        after: EventPosition | None = None,
        limit: int | None = None,
    ) -> list[EventLogEntry]:
        selected: list[EventLogEntry] = []
        for position, entry in self._entries:
            if after is not None and position <= after:
                continue
            if not _matches(entry, run_id=run_id, session_id=session_id):
                continue
            selected.append(entry)
            if limit is not None and len(selected) >= limit:
                break
        return selected

    def subscribe(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        after: EventPosition | None = None,
    ) -> AsyncIterator[EventLogEntry]:
        async def stream() -> AsyncIterator[EventLogEntry]:
            subscriber = _Subscriber(run_id=run_id, session_id=session_id)
            self._subscribers.append(subscriber)
            try:
                for entry in self.query(run_id=run_id, session_id=session_id, after=after):
                    yield entry
                while True:
                    yield await subscriber.queue.get()
            finally:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return stream()


def _matches(entry: EventLogEntry, *, run_id: str | None, session_id: str | None) -> bool:
    if run_id is not None and entry.run_id != run_id:
        return False
    if session_id is not None and entry.session_id != session_id:
        return False
    return True


__all__ = [
    "EventLogBackend",
    "EventLogEntry",
    "EventPosition",
    "InMemoryEventLogBackend",
]
