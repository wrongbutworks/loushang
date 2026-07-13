from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ConfigIssue:
    layer: str
    message: str
    error: Exception


@dataclass(frozen=True)
class ConfigApplyResult(Generic[T]):
    value: T
    issues: tuple[ConfigIssue, ...] = ()


class ConfigCodec(Protocol, Generic[T]):
    def default(self) -> T: ...

    def encode(self, value: T) -> Mapping[str, object]: ...

    def apply(
        self,
        value: T,
        patch: Mapping[str, object],
        *,
        layer: str,
    ) -> ConfigApplyResult[T]: ...


class ConfigStore(Protocol):
    def load(self, path: Path) -> Mapping[str, object]: ...

    def save(self, path: Path, patch: Mapping[str, object]) -> None: ...


@dataclass(frozen=True)
class ConfigLayer:
    name: str
    path: Path | None = None
    persistent: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("config layer name must not be empty")
        if self.path is not None:
            object.__setattr__(self, "path", Path(self.path))


@dataclass(frozen=True)
class ConfigSnapshot(Generic[T]):
    value: T
    patches: Mapping[str, Mapping[str, object]] = field(default_factory=dict)


__all__ = [
    "ConfigApplyResult",
    "ConfigCodec",
    "ConfigIssue",
    "ConfigLayer",
    "ConfigSnapshot",
    "ConfigStore",
]
