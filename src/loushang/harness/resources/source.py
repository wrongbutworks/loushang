from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Literal, TypeVar

SourceScope = Literal["user", "project", "temporary"]
SourceOrigin = Literal["package", "top-level"]
SourcePathT = TypeVar("SourcePathT", str, Path)


@dataclass(frozen=True)
class SourceInfo(Generic[SourcePathT]):
    path: SourcePathT
    source: str = "filesystem"
    scope: SourceScope = "project"
    origin: SourceOrigin = "top-level"
    base_dir: SourcePathT | None = None
