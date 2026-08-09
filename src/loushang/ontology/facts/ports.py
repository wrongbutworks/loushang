"""Ports and stable commit values for the semantic fact authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from loushang.ontology.facts.model import FactBatch, FactRecord, FactValidationError


class FactBatchConflictError(FactValidationError):
    """Raised when an idempotency key is reused with different fact content."""


@dataclass(frozen=True, slots=True)
class StoredFact:
    """One committed semantic fact and its contiguous store sequence."""

    sequence: int
    fact: FactRecord


@dataclass(frozen=True, slots=True)
class FactCommit:
    """Stable result of one atomic fact-batch commit."""

    batch_id: str
    first_sequence: int
    last_sequence: int
    fact_count: int
    replayed: bool = False


@runtime_checkable
class FactReadStore(Protocol):
    """Bitemporal read side of the semantic fact authority."""

    @property
    def fact_watermark(self) -> int: ...

    def get_fact(self, fact_id: UUID) -> StoredFact: ...

    def read_facts(self, *, after_sequence: int = 0) -> tuple[StoredFact, ...]: ...

    def facts_as_of(
        self,
        *,
        valid_at: float,
        recorded_at: float,
    ) -> tuple[StoredFact, ...]: ...


@runtime_checkable
class FactStore(FactReadStore, Protocol):
    """Atomic append side of the semantic fact authority."""

    def commit_fact_batch(self, batch: FactBatch) -> FactCommit: ...


__all__ = [
    "FactBatchConflictError",
    "FactCommit",
    "FactReadStore",
    "FactStore",
    "StoredFact",
]
