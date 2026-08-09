"""Append-only semantic FactStore port and Memory reference implementation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable
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


@dataclass(frozen=True, slots=True)
class _CommittedBatch:
    digest: str
    commit: FactCommit


@dataclass(frozen=True, slots=True)
class _FactCommitPlan:
    batch: FactBatch
    digest: str
    entries: tuple[StoredFact, ...]
    commit: FactCommit


class MemoryFactStore:
    """Deterministic in-memory reference implementation of :class:`FactStore`."""

    def __init__(self) -> None:
        self._facts: list[StoredFact] = []
        self._by_id: dict[UUID, StoredFact] = {}
        self._successors: dict[UUID, UUID] = {}
        self._batches: dict[str, _CommittedBatch] = {}

    @property
    def fact_watermark(self) -> int:
        return len(self._facts)

    def get_fact(self, fact_id: UUID) -> StoredFact:
        try:
            return self._by_id[fact_id]
        except KeyError as exc:
            raise KeyError(f"Unknown ontology fact {fact_id}") from exc

    def read_facts(self, *, after_sequence: int = 0) -> tuple[StoredFact, ...]:
        _require_sequence("after_sequence", after_sequence)
        return tuple(item for item in self._facts if item.sequence > after_sequence)

    def facts_as_of(
        self,
        *,
        valid_at: float,
        recorded_at: float,
    ) -> tuple[StoredFact, ...]:
        valid_at = _require_timestamp("valid_at", valid_at)
        recorded_at = _require_timestamp("recorded_at", recorded_at)
        retired = {
            predecessor
            for item in self._facts
            if item.fact.recorded_at <= recorded_at
            if (predecessor := item.fact.predecessor_id) is not None
        }
        return tuple(
            item
            for item in self._facts
            if item.fact.recorded_at <= recorded_at
            and item.fact.is_valid_at(valid_at)
            and item.fact.fact_id not in retired
        )

    def commit_fact_batch(self, batch: FactBatch) -> FactCommit:
        plan = self._plan_commit(batch)
        self._apply_commit(plan)
        return plan.commit

    def _plan_commit(self, batch: FactBatch) -> _FactCommitPlan:
        if not isinstance(batch, FactBatch):
            raise FactValidationError("commit_fact_batch requires a FactBatch")
        digest = batch.content_digest
        existing = self._batches.get(batch.batch_id)
        if existing is not None:
            if existing.digest != digest:
                raise FactBatchConflictError(
                    f"Fact batch '{batch.batch_id}' was already committed with other content"
                )
            return _FactCommitPlan(
                batch=batch,
                digest=digest,
                entries=(),
                commit=FactCommit(
                    batch_id=existing.commit.batch_id,
                    first_sequence=existing.commit.first_sequence,
                    last_sequence=existing.commit.last_sequence,
                    fact_count=existing.commit.fact_count,
                    replayed=True,
                ),
            )

        known = dict(self._by_id)
        successors = dict(self._successors)
        entries: list[StoredFact] = []
        next_sequence = self.fact_watermark + 1
        for offset, fact in enumerate(batch.facts):
            if fact.fact_id in known:
                raise FactValidationError(
                    f"ontology fact_id {fact.fact_id} is already committed"
                )
            predecessor_id = fact.predecessor_id
            if predecessor_id is not None:
                predecessor = known.get(predecessor_id)
                if predecessor is None:
                    raise FactValidationError(
                        f"ontology fact {fact.fact_id} references unknown predecessor "
                        f"{predecessor_id}"
                    )
                _validate_lineage(predecessor.fact, fact)
                if predecessor_id in successors:
                    raise FactValidationError(
                        f"ontology fact {predecessor_id} already has a successor"
                    )
                successors[predecessor_id] = fact.fact_id
            entry = StoredFact(sequence=next_sequence + offset, fact=fact)
            entries.append(entry)
            known[fact.fact_id] = entry

        commit = FactCommit(
            batch_id=batch.batch_id,
            first_sequence=entries[0].sequence,
            last_sequence=entries[-1].sequence,
            fact_count=len(entries),
        )
        return _FactCommitPlan(
            batch=batch,
            digest=digest,
            entries=tuple(entries),
            commit=commit,
        )

    def _apply_commit(self, plan: _FactCommitPlan) -> None:
        if plan.commit.replayed:
            return
        for entry in plan.entries:
            self._facts.append(entry)
            self._by_id[entry.fact.fact_id] = entry
            predecessor_id = entry.fact.predecessor_id
            if predecessor_id is not None:
                self._successors[predecessor_id] = entry.fact.fact_id
        self._batches[plan.batch.batch_id] = _CommittedBatch(
            digest=plan.digest,
            commit=plan.commit,
        )

    def _restore_committed_state(
        self,
        entries: tuple[StoredFact, ...],
        batches: dict[str, tuple[str, FactCommit]],
    ) -> None:
        if self._facts or self._batches:
            raise RuntimeError("MemoryFactStore already contains committed state")
        known: dict[UUID, StoredFact] = {}
        successors: dict[UUID, UUID] = {}
        for expected_sequence, entry in enumerate(entries, start=1):
            if entry.sequence != expected_sequence:
                raise FactValidationError("stored fact sequence is not contiguous")
            if entry.fact.fact_id in known:
                raise FactValidationError("stored ontology fact_id is duplicated")
            predecessor_id = entry.fact.predecessor_id
            if predecessor_id is not None:
                predecessor = known.get(predecessor_id)
                if predecessor is None:
                    raise FactValidationError("stored fact lineage is not append-only")
                _validate_lineage(predecessor.fact, entry.fact)
                if predecessor_id in successors:
                    raise FactValidationError("stored fact has multiple successors")
                successors[predecessor_id] = entry.fact.fact_id
            known[entry.fact.fact_id] = entry

        self._facts.extend(entries)
        self._by_id.update(known)
        self._successors.update(successors)
        for batch_id, (digest, commit) in batches.items():
            if batch_id != commit.batch_id or commit.replayed:
                raise FactValidationError("stored fact batch metadata is invalid")
            if commit.fact_count <= 0:
                raise FactValidationError("stored fact batch is empty")
            if commit.last_sequence - commit.first_sequence + 1 != commit.fact_count:
                raise FactValidationError("stored fact batch range is invalid")
            if commit.first_sequence < 1 or commit.last_sequence > self.fact_watermark:
                raise FactValidationError("stored fact batch range is outside the fact journal")
            self._batches[batch_id] = _CommittedBatch(digest=digest, commit=commit)


def _validate_lineage(predecessor: FactRecord, successor: FactRecord) -> None:
    predecessor_coordinate = predecessor.lineage_coordinate
    successor_coordinate = successor.lineage_coordinate
    if predecessor_coordinate[:4] != successor_coordinate[:4]:
        raise FactValidationError("fact lineage must preserve its assertion coordinate")
    if predecessor_coordinate[4:] != successor_coordinate[4:]:
        raise FactValidationError("fact lineage must preserve its source lineage")
    if successor.recorded_at < predecessor.recorded_at:
        raise FactValidationError(
            "fact lineage successor recorded_at cannot precede its predecessor"
        )


def _require_sequence(name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _require_timestamp(name: str, value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    number = cast(int | float, value)
    if not math.isfinite(float(number)):
        raise ValueError(f"{name} must be a finite number")
    return float(number)


__all__ = [
    "FactBatchConflictError",
    "FactCommit",
    "FactReadStore",
    "FactStore",
    "MemoryFactStore",
    "StoredFact",
]
