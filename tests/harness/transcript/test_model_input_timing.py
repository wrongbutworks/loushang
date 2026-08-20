from __future__ import annotations

import pytest

from loushang.harness.transcript.model_input_timing import PhaseTimer


class _Clock:
    def __init__(self, *values: int) -> None:
        self._values = iter(values)

    def __call__(self) -> int:
        return next(self._values)


def test_phase_timer_aggregates_repeated_phases() -> None:
    timer = PhaseTimer(clock=_Clock(0, 10, 40, 50, 90, 100))

    with timer.phase("materialize"):
        pass
    with timer.phase("materialize"):
        pass

    snapshot = timer.snapshot()

    assert snapshot.total_ns == 100
    assert snapshot.phases["materialize"].total_ns == 70
    assert snapshot.phases["materialize"].count == 2


def test_phase_timer_records_a_phase_that_raises() -> None:
    timer = PhaseTimer(clock=_Clock(0, 10, 25, 30))

    with pytest.raises(RuntimeError, match="failed"):
        with timer.phase("append"):
            raise RuntimeError("failed")

    snapshot = timer.snapshot()

    assert snapshot.total_ns == 30
    assert snapshot.phases["append"].total_ns == 15
    assert snapshot.phases["append"].count == 1


def test_phase_timer_rejects_nested_phases() -> None:
    timer = PhaseTimer(clock=_Clock(0, 10, 20))

    with timer.phase("outer"):
        with pytest.raises(RuntimeError, match="outer.*already active"):
            with timer.phase("inner"):
                pass
