from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import time_ns
from typing import Any, Generic, Protocol, TypeVar, cast

P = TypeVar("P")


class ProjectionCodec(Protocol, Generic[P]):
    def encode(self, projection: P) -> Mapping[str, object]: ...

    def decode(self, value: Mapping[str, object]) -> P: ...


@dataclass(frozen=True)
class FunctionalProjectionCodec(Generic[P]):
    encoder: Callable[[P], Mapping[str, object]]
    decoder: Callable[[Mapping[str, object]], P]

    def encode(self, projection: P) -> Mapping[str, object]:
        return self.encoder(projection)

    def decode(self, value: Mapping[str, object]) -> P:
        return self.decoder(value)


@dataclass(frozen=True)
class ProjectionIndexSnapshot(Generic[P]):
    projections: tuple[P, ...]
    stale: bool = False


class JsonProjectionIndex(Generic[P]):
    def __init__(
        self,
        path: str | Path,
        *,
        version: int,
        codec: ProjectionCodec[P],
        items_key: str = "items",
        is_current: Callable[[P], bool] | None = None,
        sort_key: Callable[[P], Any] | None = None,
        reverse: bool = False,
        generated_at: Callable[[], str] | None = None,
    ) -> None:
        if version < 1:
            raise ValueError("projection index version must be positive")
        if not items_key:
            raise ValueError("projection index items key must not be empty")
        self.path = Path(path)
        self.version = version
        self.codec = codec
        self.items_key = items_key
        self.is_current = is_current
        self.sort_key = sort_key
        self.reverse = reverse
        self.generated_at = generated_at or _now_iso

    def write(self, projections: Sequence[P]) -> tuple[P, ...]:
        ordered = self._sort(projections)
        payload = {
            "version": self.version,
            "generated_at": self.generated_at(),
            self.items_key: [dict(self.codec.encode(item)) for item in ordered],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        except BaseException:
            with suppress(FileNotFoundError):
                temp_path.unlink()
            raise
        return ordered

    def load(self) -> ProjectionIndexSnapshot[P]:
        if not self.path.exists():
            return ProjectionIndexSnapshot(())
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.preserve_corrupt()
            return ProjectionIndexSnapshot((), stale=True)
        if not isinstance(payload, Mapping) or payload.get("version") != self.version:
            return ProjectionIndexSnapshot((), stale=True)
        raw_items = payload.get(self.items_key)
        if not isinstance(raw_items, list):
            return ProjectionIndexSnapshot((), stale=True)

        projections: list[P] = []
        stale = False
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping):
                stale = True
                continue
            try:
                projection = self.codec.decode(cast(Mapping[str, object], raw_item))
            except Exception:
                stale = True
                continue
            if self.is_current is not None and not self.is_current(projection):
                stale = True
                continue
            projections.append(projection)
        return ProjectionIndexSnapshot(self._sort(projections), stale=stale)

    def load_or_refresh(
        self,
        build: Callable[[], Sequence[P]],
        *,
        refresh: bool = False,
        refresh_empty: bool = True,
    ) -> tuple[P, ...]:
        if not refresh:
            snapshot = self.load()
            if not snapshot.stale and (snapshot.projections or not refresh_empty):
                return snapshot.projections
        return self.write(build())

    def preserve_corrupt(self) -> Path | None:
        if not self.path.exists():
            return None
        target = self.path.with_name(f"{self.path.name}.corrupt-{time_ns()}")
        try:
            self.path.replace(target)
        except Exception:
            return None
        return target

    def _sort(self, projections: Sequence[P]) -> tuple[P, ...]:
        if self.sort_key is None:
            return tuple(projections)
        return tuple(sorted(projections, key=self.sort_key, reverse=self.reverse))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "FunctionalProjectionCodec",
    "JsonProjectionIndex",
    "ProjectionCodec",
    "ProjectionIndexSnapshot",
]
