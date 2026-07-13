from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Generic, TypeVar

from loushang.harness.journal.branch import BranchGraph, BranchMode
from loushang.harness.journal.jsonl import JsonlJournal
from loushang.harness.journal.types import JournalDiagnostic, JsonlSnapshot

H = TypeVar("H")
R = TypeVar("R")


class TranscriptRepository(Generic[H, R]):
    """In-memory parent-linked transcript state backed by an optional journal."""

    def __init__(
        self,
        *,
        header: H,
        records: Sequence[R],
        record_id: Callable[[R], str],
        parent_id: Callable[[R], str | None],
        journal: JsonlJournal[H, R] | None = None,
        mode: BranchMode = "strict",
        diagnostics: Sequence[JournalDiagnostic] = (),
        leaf_id: str | None = None,
    ) -> None:
        self._header = header
        self._records = list(records)
        self._record_id = record_id
        self._parent_id = parent_id
        self._journal = journal
        self._mode = mode
        self._load_diagnostics = tuple(diagnostics)
        self._graph = self._build_graph(self._records)
        self._leaf_id = self._resolve_initial_leaf(leaf_id)

    @classmethod
    def create(
        cls,
        *,
        header: H,
        records: Sequence[R] = (),
        record_id: Callable[[R], str],
        parent_id: Callable[[R], str | None],
        journal: JsonlJournal[H, R] | None = None,
        mode: BranchMode = "strict",
        leaf_id: str | None = None,
    ) -> TranscriptRepository[H, R]:
        repository = cls(
            header=header,
            records=records,
            record_id=record_id,
            parent_id=parent_id,
            journal=journal,
            mode=mode,
            leaf_id=leaf_id,
        )
        if journal is not None:
            journal.rewrite(repository.records, header=header)
        return repository

    @classmethod
    def load(
        cls,
        journal: JsonlJournal[H, R],
        *,
        record_id: Callable[[R], str],
        parent_id: Callable[[R], str | None],
        mode: BranchMode = "strict",
        writable: bool = True,
    ) -> TranscriptRepository[H, R]:
        snapshot: JsonlSnapshot[H, R] = journal.load()
        if snapshot.header is None:
            raise ValueError("transcript journal requires a header")
        return cls(
            header=snapshot.header,
            records=snapshot.records,
            record_id=record_id,
            parent_id=parent_id,
            journal=journal if writable else None,
            mode=mode,
            diagnostics=snapshot.diagnostics,
        )

    @property
    def header(self) -> H:
        return self._header

    @property
    def path(self) -> Path | None:
        return self._journal.path if self._journal is not None else None

    @property
    def records(self) -> tuple[R, ...]:
        return tuple(self._records)

    @property
    def leaf_id(self) -> str | None:
        return self._leaf_id

    @property
    def diagnostics(self) -> tuple[JournalDiagnostic, ...]:
        return (*self._load_diagnostics, *self._graph.diagnostics)

    def set_header(self, header: H, *, rewrite: bool = False) -> None:
        if rewrite and self._journal is not None:
            self._journal.rewrite(self._records, header=header)
        self._header = header

    def get(self, record_id: str) -> R | None:
        return self._graph.get(record_id)

    def leaf(self) -> R | None:
        return self.get(self._leaf_id) if self._leaf_id is not None else None

    def children(self, record_id: str) -> tuple[R, ...]:
        if self._graph.get(record_id) is None:
            return ()
        return self._graph.children(record_id)

    def path_to(self, record_id: str | None = None) -> tuple[R, ...]:
        selected_id = self._leaf_id if record_id is None else record_id
        if selected_id is None:
            return ()
        return self._graph.path(selected_id)

    def roots(self) -> tuple[R, ...]:
        return self._graph.roots()

    def select_leaf(self, record_id: str) -> None:
        if self._graph.get(record_id) is None:
            raise ValueError(f"Transcript record {record_id} not found")
        self._leaf_id = record_id

    def reset_leaf(self) -> None:
        self._leaf_id = None

    def append(self, record: R) -> str:
        candidate_records = [*self._records, record]
        candidate_graph = self._build_graph(candidate_records)
        record_id = self._record_id(record)
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("Transcript record id must be a non-empty string")
        if self._journal is not None:
            self._journal.append(record)
        self._records = candidate_records
        self._graph = candidate_graph
        self._leaf_id = record_id
        return record_id

    def rewrite(self) -> None:
        if self._journal is not None:
            self._journal.rewrite(self._records, header=self._header)

    def fork(
        self,
        *,
        header: H,
        journal: JsonlJournal[H, R] | None,
        leaf_id: str | None = None,
    ) -> TranscriptRepository[H, R]:
        selected_id = self._leaf_id if leaf_id is None else leaf_id
        records = self.path_to(selected_id) if selected_id is not None else ()
        return type(self).create(
            header=header,
            records=records,
            record_id=self._record_id,
            parent_id=self._parent_id,
            journal=journal,
            mode=self._mode,
        )

    def _build_graph(self, records: Sequence[R]) -> BranchGraph[R]:
        return BranchGraph(
            records,
            record_id=self._record_id,
            parent_id=self._parent_id,
            mode=self._mode,
        )

    def _resolve_initial_leaf(self, leaf_id: str | None) -> str | None:
        if leaf_id is not None:
            if self._graph.get(leaf_id) is None:
                raise ValueError(f"Transcript record {leaf_id} not found")
            return leaf_id
        if not self._records:
            return None
        candidate = self._record_id(self._records[-1])
        return candidate if self._graph.get(candidate) is not None else None


__all__ = ["TranscriptRepository"]
