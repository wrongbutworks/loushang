from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar, runtime_checkable

from loushang.harness.storage.types import (
    CommitReceipt,
    ConversationKey,
    ConversationSnapshot,
)

HeaderT = TypeVar("HeaderT")
RecordT = TypeVar("RecordT")


@runtime_checkable
class ConversationStore(Protocol[HeaderT, RecordT]):
    """Asynchronous persistence port for one conversation record stream."""

    async def create(
        self,
        key: ConversationKey,
        header: HeaderT,
        records: Sequence[RecordT] = (),
    ) -> ConversationSnapshot[HeaderT, RecordT]: ...

    async def load(
        self,
        key: ConversationKey,
    ) -> ConversationSnapshot[HeaderT, RecordT]: ...

    async def append(
        self,
        key: ConversationKey,
        record: RecordT,
        *,
        expected_revision: int,
    ) -> CommitReceipt: ...

    async def delete(self, key: ConversationKey) -> None: ...

    async def scan(self, namespace: str) -> tuple[ConversationKey, ...]: ...


__all__ = ["ConversationStore"]
