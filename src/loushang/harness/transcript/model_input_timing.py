"""Low-overhead aggregate timing for Model Input commit phases."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType

NanosecondClock = Callable[[], int]


@dataclass(frozen=True, slots=True)
class PhaseMeasurement:
    """Accumulated duration and invocation count for one named phase."""

    total_ns: int
    count: int


@dataclass(frozen=True, slots=True)
class PhaseTimingSnapshot:
    """One immutable aggregate timing result."""

    total_ns: int
    phases: Mapping[str, PhaseMeasurement]


class PhaseTimer:
    """Measure sequential phases in memory using an injectable monotonic clock."""

    def __init__(
        self,
        *,
        clock: NanosecondClock = time.perf_counter_ns,
    ) -> None:
        self._clock = clock
        self._started_ns = clock()
        self._durations: dict[str, int] = {}
        self._counts: dict[str, int] = {}
        self._active_phase: str | None = None

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Measure one phase, recording it even when the body raises."""

        normalized = name.strip()
        if not normalized:
            raise ValueError("timing phase name must be non-empty")
        if self._active_phase is not None:
            raise RuntimeError(f"timing phase {self._active_phase!r} is already active")
        self._active_phase = normalized
        started_ns = self._clock()
        try:
            yield
        finally:
            duration_ns = self._clock() - started_ns
            self._active_phase = None
            self._durations[normalized] = (
                self._durations.get(normalized, 0) + duration_ns
            )
            self._counts[normalized] = self._counts.get(normalized, 0) + 1

    def snapshot(self) -> PhaseTimingSnapshot:
        """Freeze the current aggregate without retaining measured objects."""

        if self._active_phase is not None:
            raise RuntimeError(
                f"cannot snapshot while timing phase {self._active_phase!r} is active"
            )
        return PhaseTimingSnapshot(
            total_ns=self._clock() - self._started_ns,
            phases=MappingProxyType(
                {
                    name: PhaseMeasurement(
                        total_ns=duration_ns,
                        count=self._counts[name],
                    )
                    for name, duration_ns in self._durations.items()
                }
            ),
        )


__all__ = ["PhaseMeasurement", "PhaseTimer", "PhaseTimingSnapshot"]
