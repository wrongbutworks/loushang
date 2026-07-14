from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from loushang.harness.conversation.ports import ConversationProjector
from loushang.harness.conversation.repository import ConversationRepository
from loushang.harness.journal import JsonProjectionIndex

H = TypeVar("H")
R = TypeVar("R")
P = TypeVar("P")


@dataclass(frozen=True)
class ProjectionQuery(Generic[P]):
    predicate: Callable[[P], bool] | None = None
    sort_key: Callable[[P], Any] | None = None
    reverse: bool = False
    limit: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reverse, bool):
            raise TypeError("projection query reverse must be a boolean")
        if self.limit is not None:
            if isinstance(self.limit, bool) or not isinstance(self.limit, int):
                raise TypeError("projection query limit must be an integer or None")
            if self.limit < 0:
                raise ValueError("projection query limit must be non-negative")

    def apply(self, projections: Iterable[P]) -> tuple[P, ...]:
        selected = (
            list(projections)
            if self.predicate is None
            else [item for item in projections if self.predicate(item)]
        )
        if self.sort_key is not None:
            selected.sort(key=self.sort_key, reverse=self.reverse)
        if self.limit is not None:
            selected = selected[: self.limit]
        return tuple(selected)


class ConversationCatalog(Generic[H, R, P]):
    """Discover and project repositories, with an optional durable index cache."""

    def __init__(
        self,
        *,
        discover: Callable[[], Iterable[ConversationRepository[H, R]]],
        projector: ConversationProjector[H, R, P],
        index: JsonProjectionIndex[P] | None = None,
        skip_projection_errors: bool = False,
        on_projection_error: (
            Callable[[ConversationRepository[H, R], Exception], None] | None
        ) = None,
    ) -> None:
        self._discover = discover
        self._projector = projector
        self._index = index
        self._skip_projection_errors = skip_projection_errors
        self._on_projection_error = on_projection_error

    def scan(self) -> tuple[P, ...]:
        projections: list[P] = []
        for repository in self._discover():
            try:
                projections.append(self._project(repository))
            except Exception as exc:
                if not self._skip_projection_errors:
                    raise
                if self._on_projection_error is not None:
                    self._on_projection_error(repository, exc)
        return tuple(projections)

    def refresh(self) -> tuple[P, ...]:
        projections = self.scan()
        if self._index is None:
            return projections
        return self._index.write(projections)

    def list(self, *, refresh: bool = False) -> tuple[P, ...]:
        if self._index is None:
            return self.scan()
        return self._index.load_or_refresh(self.scan, refresh=refresh)

    def query(
        self,
        query: ProjectionQuery[P] | None = None,
        *,
        refresh: bool = False,
    ) -> tuple[P, ...]:
        return (query or ProjectionQuery()).apply(self.list(refresh=refresh))

    def _project(self, repository: ConversationRepository[H, R]) -> P:
        return self._projector.project(
            header=repository.header,
            records=repository.records,
            leaf_id=repository.leaf_id,
            source_path=repository.path,
        )


__all__ = ["ConversationCatalog", "ProjectionQuery"]
