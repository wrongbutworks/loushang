from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SelectionRange"]


@dataclass(frozen=True, slots=True)
class SelectionRange:
    anchor: int
    focus: int

    @property
    def start(self) -> int:
        return min(self.anchor, self.focus)

    @property
    def end(self) -> int:
        return max(self.anchor, self.focus)

    @property
    def is_empty(self) -> bool:
        return self.anchor == self.focus

    def normalized(self, length: int) -> tuple[int, int]:
        length = max(0, length)
        start = max(0, min(self.start, length))
        end = max(0, min(self.end, length))
        if end < start:
            end = start
        return start, end
