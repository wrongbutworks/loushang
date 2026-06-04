from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

__all__ = ["KillRing"]


@dataclass(slots=True)
class KillRing:
    max_entries: int = 20
    _ring: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.max_entries <= 0:
            raise ValueError("max_entries must be positive")

    def __bool__(self) -> bool:
        return bool(self._ring)

    def __iter__(self) -> Iterator[str]:
        return iter(self._ring)

    def __len__(self) -> int:
        return len(self._ring)

    def push(self, text: str, *, prepend: bool, accumulate: bool = False) -> None:
        if not text:
            return
        if accumulate and self._ring:
            last = self._ring.pop()
            self._ring.append(f"{text}{last}" if prepend else f"{last}{text}")
        else:
            self._ring.append(text)
        del self._ring[:-self.max_entries]

    def peek(self) -> str | None:
        if not self._ring:
            return None
        return self._ring[-1]

    def rotate(self) -> None:
        if len(self._ring) <= 1:
            return
        self._ring.insert(0, self._ring.pop())

    def clear(self) -> None:
        self._ring.clear()
