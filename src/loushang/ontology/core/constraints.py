"""Stable diagnostics for explicit ontology snapshot integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IntegrityViolation:
    code: str
    object_id: UUID | None
    path: str
    message: str


__all__ = ["IntegrityViolation"]
