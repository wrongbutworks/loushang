from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSelection:
    """Stable reference to a configured model and optional endpoint."""

    provider: str
    model_id: str
    endpoint_id: str | None = None


__all__ = ["ModelSelection"]
