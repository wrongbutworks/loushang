from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model_id: str
    endpoint_id: str | None = None


__all__ = ["ModelSelection"]
