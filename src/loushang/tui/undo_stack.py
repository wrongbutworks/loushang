from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

__all__ = ["UndoStack"]

T = TypeVar("T")


@dataclass(slots=True)
class UndoStack(Generic[T]):
    max_depth: int | None = None
    _stack: list[T] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.max_depth is not None and self.max_depth <= 0:
            raise ValueError("max_depth must be positive or None")

    def __bool__(self) -> bool:
        return bool(self._stack)

    def __len__(self) -> int:
        return len(self._stack)

    def push(self, snapshot: T) -> None:
        self._stack.append(snapshot)
        if self.max_depth is not None:
            del self._stack[:-self.max_depth]

    def pop(self) -> T | None:
        if not self._stack:
            return None
        return self._stack.pop()

    def clear(self) -> None:
        self._stack.clear()
