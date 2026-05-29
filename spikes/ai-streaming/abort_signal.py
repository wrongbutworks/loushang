from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AbortSignalLike(Protocol):
    cancelled: bool


@dataclass(slots=True)
class ManualAbortSignal:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True

