from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from loushang.harness.conversation.store import ConversationLocator

ProjectionT = TypeVar("ProjectionT")
QueryT = TypeVar("QueryT")


@dataclass(frozen=True)
class IndexedProjection(Generic[ProjectionT]):
    """One rebuildable projection tied to its authoritative source revision."""

    locator: ConversationLocator
    source_revision: int
    projection: ProjectionT


class ConversationIndex(Protocol[ProjectionT, QueryT]):
    async def upsert(self, item: IndexedProjection[ProjectionT]) -> bool: ...

    async def delete(
        self,
        locator: ConversationLocator,
        *,
        through_revision: int,
    ) -> bool: ...

    async def get(
        self,
        locator: ConversationLocator,
    ) -> IndexedProjection[ProjectionT] | None: ...

    async def query(
        self,
        query: QueryT,
    ) -> Sequence[IndexedProjection[ProjectionT]]: ...

    async def replace(
        self,
        items: Sequence[IndexedProjection[ProjectionT]],
    ) -> tuple[IndexedProjection[ProjectionT], ...]: ...


IndexQuery = Callable[
    [QueryT, Sequence[IndexedProjection[ProjectionT]]],
    Sequence[IndexedProjection[ProjectionT]],
]


class MemoryConversationIndex(Generic[ProjectionT, QueryT]):
    """Reference rebuildable index with revision and deletion ordering."""

    def __init__(
        self,
        *,
        query_items: IndexQuery[ProjectionT, QueryT],
    ) -> None:
        self._query_items = query_items
        self._items: dict[ConversationLocator, IndexedProjection[ProjectionT]] = {}
        self._tombstones: dict[ConversationLocator, int] = {}

    async def upsert(self, item: IndexedProjection[ProjectionT]) -> bool:
        tombstone = self._tombstones.get(item.locator, -1)
        current = self._items.get(item.locator)
        if item.source_revision <= tombstone:
            return False
        if current is not None and item.source_revision < current.source_revision:
            return False
        self._items[item.locator] = item
        return True

    async def delete(
        self,
        locator: ConversationLocator,
        *,
        through_revision: int,
    ) -> bool:
        previous = self._tombstones.get(locator, -1)
        if through_revision < previous:
            return False
        self._tombstones[locator] = through_revision
        current = self._items.get(locator)
        if current is not None and current.source_revision <= through_revision:
            del self._items[locator]
        return through_revision > previous

    async def get(
        self,
        locator: ConversationLocator,
    ) -> IndexedProjection[ProjectionT] | None:
        return self._items.get(locator)

    async def query(
        self,
        query: QueryT,
    ) -> Sequence[IndexedProjection[ProjectionT]]:
        return tuple(self._query_items(query, tuple(self._items.values())))

    async def replace(
        self,
        items: Sequence[IndexedProjection[ProjectionT]],
    ) -> tuple[IndexedProjection[ProjectionT], ...]:
        replacement = {
            item.locator: item
            for item in items
            if item.source_revision > self._tombstones.get(item.locator, -1)
        }
        self._items = replacement
        return tuple(replacement.values())


__all__ = [
    "ConversationIndex",
    "IndexQuery",
    "IndexedProjection",
    "MemoryConversationIndex",
]
