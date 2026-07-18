from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Generic, TypeVar

from loushang.harness.storage.errors import (
    StoreAlreadyExistsError,
    StoreConflictError,
    StoreNotFoundError,
)
from loushang.harness.storage.types import (
    CommitReceipt,
    ConversationKey,
    ConversationSnapshot,
    require_revision,
)

HeaderT = TypeVar("HeaderT")
RecordT = TypeVar("RecordT")
Clock = Callable[[], datetime]
RecordId = Callable[[RecordT], str | None]


class MemoryConversationStore(Generic[HeaderT, RecordT]):
    """Deterministic in-memory implementation of ``ConversationStore``."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        record_id: RecordId[RecordT] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._record_id = record_id
        self._snapshots: dict[
            ConversationKey,
            ConversationSnapshot[HeaderT, RecordT],
        ] = {}

    async def create(
        self,
        key: ConversationKey,
        header: HeaderT,
        records: Sequence[RecordT] = (),
    ) -> ConversationSnapshot[HeaderT, RecordT]:
        if key in self._snapshots:
            raise StoreAlreadyExistsError(f"conversation {key!r} already exists")
        snapshot = ConversationSnapshot(
            header=header,
            records=records,
            revision=len(records),
        )
        self._snapshots[key] = snapshot
        return snapshot

    async def load(
        self,
        key: ConversationKey,
    ) -> ConversationSnapshot[HeaderT, RecordT]:
        try:
            return self._snapshots[key]
        except KeyError as exc:
            raise StoreNotFoundError(f"conversation {key!r} was not found") from exc

    async def append(
        self,
        key: ConversationKey,
        record: RecordT,
        *,
        expected_revision: int,
    ) -> CommitReceipt:
        expected = require_revision(expected_revision, name="expected revision")
        snapshot = await self.load(key)
        if snapshot.revision != expected:
            raise StoreConflictError(
                f"conversation {key!r} is at revision {snapshot.revision}, "
                f"not {expected}"
            )
        revision = snapshot.revision + 1
        receipt = CommitReceipt(
            revision=revision,
            committed_at=self._clock(),
            record_id=self._record_id(record) if self._record_id is not None else None,
        )
        self._snapshots[key] = ConversationSnapshot(
            header=snapshot.header,
            records=(*snapshot.records, record),
            revision=revision,
        )
        return receipt

    async def delete(self, key: ConversationKey) -> None:
        try:
            del self._snapshots[key]
        except KeyError as exc:
            raise StoreNotFoundError(f"conversation {key!r} was not found") from exc

    async def scan(self, namespace: str) -> tuple[ConversationKey, ...]:
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValueError("conversation namespace must be a non-empty string")
        return tuple(
            sorted(key for key in self._snapshots if key.namespace == namespace)
        )


__all__ = ["MemoryConversationStore"]
