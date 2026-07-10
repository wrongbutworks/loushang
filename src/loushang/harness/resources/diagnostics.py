from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

_EMPTY_METADATA: Mapping[str, object] = MappingProxyType({})


@dataclass(frozen=True)
class ResourceDiagnostic:
    code: str
    message: str
    source_path: Path | None = None
    resource_id: str | None = None
    resource_type: str | None = None
    source_kind: str | None = None
    metadata: Mapping[str, object] = field(default_factory=lambda: _EMPTY_METADATA)
