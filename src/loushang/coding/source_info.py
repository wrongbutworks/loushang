from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

SourceScope = Literal["user", "project", "temporary"]
SourceOrigin = Literal["package", "top-level"]


@dataclass(frozen=True)
class SourceInfo:
    path: str
    source: str = "filesystem"
    scope: SourceScope = "project"
    origin: SourceOrigin = "top-level"
    base_dir: str | None = None


class SourceDescriptor(Protocol):
    source_path: Path
    source: str
    source_kind: str
    source_scope: str
    source_root: Path | None


def create_source_info(
    path: str | Path,
    *,
    source: str = "filesystem",
    scope: SourceScope = "project",
    origin: SourceOrigin = "top-level",
    base_dir: str | Path | None = None,
) -> SourceInfo:
    return SourceInfo(
        path=_path_text(path),
        source=source,
        scope=scope,
        origin=origin,
        base_dir=_path_text(base_dir) if base_dir is not None else None,
    )


def source_info_from_resource_descriptor(descriptor: SourceDescriptor) -> SourceInfo:
    return create_source_info(
        descriptor.source_path,
        source=descriptor.source or "filesystem",
        scope=_scope_from_descriptor(source_scope=descriptor.source_scope, source_kind=descriptor.source_kind),
        origin=_origin_from_descriptor(source_scope=descriptor.source_scope, source_kind=descriptor.source_kind),
        base_dir=descriptor.source_root if descriptor.source_root is not None else descriptor.source_path.parent,
    )


def _scope_from_descriptor(*, source_scope: object, source_kind: object) -> SourceScope:
    if source_scope == "user":
        return "user"
    if source_kind == "temporary" or source_scope == "temporary":
        return "temporary"
    return "project"


def _origin_from_descriptor(*, source_scope: object, source_kind: object) -> SourceOrigin:
    if source_scope in {"package", "builtin"} or source_kind in {"external_package", "built_in"}:
        return "package"
    return "top-level"


def _path_text(path: str | Path | object) -> str:
    if isinstance(path, Path):
        return path.as_posix()
    if isinstance(path, str):
        return path
    return str(path)
