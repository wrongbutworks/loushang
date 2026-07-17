from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

HeaderT = TypeVar("HeaderT")
RecordT = TypeVar("RecordT")


def _require_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def require_revision(value: object, *, name: str = "revision") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


@dataclass(frozen=True, order=True)
class ConversationKey:
    """Backend-neutral identity for a stored conversation."""

    namespace: str
    conversation_id: str

    def __post_init__(self) -> None:
        _require_text(self.namespace, name="conversation namespace")
        _require_text(self.conversation_id, name="conversation id")


@dataclass(frozen=True)
class ConversationSnapshot(Generic[HeaderT, RecordT]):
    """One authoritative conversation snapshot and its concurrency token."""

    header: HeaderT
    records: tuple[RecordT, ...]
    revision: int

    def __init__(
        self,
        *,
        header: HeaderT,
        records: Sequence[RecordT],
        revision: int,
    ) -> None:
        durable_records = tuple(records)
        normalized_revision = require_revision(revision)
        if normalized_revision != len(durable_records):
            raise ValueError("snapshot revision must equal its record count")
        object.__setattr__(self, "header", header)
        object.__setattr__(self, "records", durable_records)
        object.__setattr__(self, "revision", normalized_revision)


@dataclass(frozen=True)
class CommitReceipt:
    """Result of one successful durable append."""

    revision: int
    committed_at: datetime
    record_id: str | None = None

    def __post_init__(self) -> None:
        require_revision(self.revision)
        if self.revision < 1:
            raise ValueError("commit receipt revision must be positive")
        if not isinstance(self.committed_at, datetime):
            raise TypeError("commit timestamp must be a datetime")
        if self.committed_at.tzinfo is None:
            raise ValueError("commit timestamp must be timezone-aware")
        if self.record_id is not None:
            _require_text(self.record_id, name="committed record id")


__all__ = [
    "CommitReceipt",
    "ConversationKey",
    "ConversationSnapshot",
    "require_revision",
]
