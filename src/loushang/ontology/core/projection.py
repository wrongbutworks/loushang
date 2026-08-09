"""Committed store mutations and rebuildable projection state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import cast

from loushang.foundation.json import JSONValue, dump_json_value


@dataclass(frozen=True, slots=True, init=False)
class StoreMutation:
    """One committed operational store mutation.

    This journal is an infrastructure recovery primitive.  It deliberately is
    not the semantic Fact/Provenance model reserved for a later ontology wave.
    """

    sequence: int
    kind: str
    timestamp: float
    _payload_json: str = field(repr=False)

    def __init__(
        self,
        *,
        sequence: int,
        kind: str,
        payload: dict[str, JSONValue],
        timestamp: float,
    ) -> None:
        object.__setattr__(self, "sequence", sequence)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(
            self,
            "_payload_json",
            dump_json_value(payload, name="ontology mutation", sort_keys=True),
        )

    @property
    def payload(self) -> dict[str, JSONValue]:
        return cast(dict[str, JSONValue], json.loads(self._payload_json))


@dataclass(frozen=True, slots=True)
class ProjectionState:
    """Freshness metadata for synchronous materialized projections."""

    schema_version: str | None
    projection_version: int
    source_watermark: int
    projected_watermark: int
    built_at: float

    @property
    def fresh(self) -> bool:
        return self.source_watermark == self.projected_watermark


__all__ = ["ProjectionState", "StoreMutation"]
