from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, cast

from loushang.harness.journal import (
    PROCESS_LOCAL_JOURNAL,
    SORTED_UNICODE_JSONL_FORMAT,
    FunctionalJournalRecordCodec,
    JournalLoadPolicy,
    JsonlJournal,
    JsonlSnapshot,
)


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


class _EventLogState:
    def __init__(self) -> None:
        self._entries: list[tuple[EventPosition, EventLogEntry]] = []
        self._subscribers: list[_Subscriber] = []

    def _append_stored(self, entry: EventLogEntry) -> EventPosition:
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


class InMemoryEventLogBackend(_EventLogState):
    def append(self, entry: EventLogEntry) -> EventPosition:
        return self._append_stored(entry)


class JsonlEventLogBackend(_EventLogState):
    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = Path(path)
        self._journal: JsonlJournal[object, EventLogEntry] = JsonlJournal(
            self._path,
            record_codec=_EVENT_LOG_CODEC,
            format_profile=SORTED_UNICODE_JSONL_FORMAT,
            durability=PROCESS_LOCAL_JOURNAL,
            load_policy=JournalLoadPolicy(),
        )
        self._load()

    def append(self, entry: EventLogEntry) -> EventPosition:
        stored_entry = _normalize_entry(entry)
        self._journal.append(stored_entry)
        return self._append_stored(stored_entry)

    def _load(self) -> None:
        if not self._path.exists():
            return
        snapshot: JsonlSnapshot[object, EventLogEntry] = self._journal.load()
        for entry in snapshot.records:
            position = EventPosition(offset=len(self._entries) + 1)
            self._entries.append((position, entry))


def _matches(entry: EventLogEntry, *, run_id: str | None, session_id: str | None) -> bool:
    if run_id is not None and entry.run_id != run_id:
        return False
    if session_id is not None and entry.session_id != session_id:
        return False
    return True


def _normalize_entry(entry: EventLogEntry) -> EventLogEntry:
    return EventLogEntry(
        entry_id=entry.entry_id,
        entry_type=entry.entry_type,
        operation_id=entry.operation_id,
        event_id=entry.event_id,
        run_id=entry.run_id,
        session_id=entry.session_id,
        sequence=entry.sequence,
        payload=cast(Mapping[str, object], _to_json_value(entry.payload)),
        created_at=entry.created_at,
    )


def _entry_to_json(entry: EventLogEntry) -> dict[str, object]:
    return {
        "entry_id": entry.entry_id,
        "entry_type": entry.entry_type,
        "operation_id": entry.operation_id,
        "event_id": entry.event_id,
        "run_id": entry.run_id,
        "session_id": entry.session_id,
        "sequence": entry.sequence,
        "payload": _to_json_value(entry.payload),
        "created_at": entry.created_at.isoformat(),
    }


def _entry_from_json(data: Mapping[str, object]) -> EventLogEntry:
    return EventLogEntry(
        entry_id=str(data["entry_id"]),
        entry_type=cast(Literal["operation", "event"], data["entry_type"]),
        operation_id=str(data["operation_id"]),
        event_id=cast(str | None, data["event_id"]),
        run_id=str(data["run_id"]),
        session_id=str(data["session_id"]),
        sequence=int(cast(int, data["sequence"])),
        payload=cast(Mapping[str, object], data["payload"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
    )


_EVENT_LOG_CODEC = FunctionalJournalRecordCodec(_entry_to_json, _entry_from_json)


def _to_json_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_json_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _to_json_value(asdict(value))
    return repr(value)


__all__ = [
    "EventLogBackend",
    "EventLogEntry",
    "EventPosition",
    "InMemoryEventLogBackend",
    "JsonlEventLogBackend",
]
