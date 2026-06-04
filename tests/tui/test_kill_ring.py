from __future__ import annotations

import pytest

from loushang.tui.kill_ring import KillRing


def test_kill_ring_push_peek_rotate_and_iterate() -> None:
    ring = KillRing()

    assert not ring
    assert ring.peek() is None

    ring.push("alpha", prepend=False)
    ring.push("beta", prepend=False)

    assert ring
    assert len(ring) == 2
    assert ring.peek() == "beta"
    assert tuple(ring) == ("alpha", "beta")

    ring.rotate()

    assert tuple(ring) == ("beta", "alpha")
    assert ring.peek() == "alpha"


def test_kill_ring_accumulates_consecutive_kills() -> None:
    ring = KillRing()

    ring.push("beta", prepend=False)
    ring.push("alpha ", prepend=True, accumulate=True)
    assert ring.peek() == "alpha beta"

    ring.push(" gamma", prepend=False, accumulate=True)
    assert ring.peek() == "alpha beta gamma"


def test_kill_ring_ignores_empty_text() -> None:
    ring = KillRing()

    ring.push("", prepend=False)

    assert not ring
    assert ring.peek() is None


def test_kill_ring_max_entries_drops_oldest_entries() -> None:
    ring = KillRing(max_entries=2)

    ring.push("one", prepend=False)
    ring.push("two", prepend=False)
    ring.push("three", prepend=False)

    assert tuple(ring) == ("two", "three")
    assert ring.peek() == "three"


def test_kill_ring_max_entries_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        KillRing(max_entries=0)

    with pytest.raises(ValueError, match="max_entries"):
        KillRing(max_entries=-1)
