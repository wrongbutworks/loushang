from __future__ import annotations

import pytest

from loushang.harness.runtime import RuntimeBindingState


def test_binding_lease_reads_refreshed_bindings_until_invalidated() -> None:
    state = RuntimeBindingState[dict[str, int]](
        unbound_message="not bound",
        stale_message="stale",
    )

    with pytest.raises(RuntimeError, match="not bound"):
        state.require()

    state.bind({"version": 1})
    lease = state.capture()
    state.refresh({"version": 2})

    assert state.is_bound is True
    assert lease.is_current is True
    assert lease.require() == {"version": 2}


def test_binding_invalidation_stales_old_leases_and_allows_new_ones() -> None:
    state = RuntimeBindingState("first", stale_message="old context")
    old = state.capture()

    state.invalidate()
    current = state.capture()

    assert old.is_current is False
    with pytest.raises(RuntimeError, match="old context"):
        old.require()
    assert current.require() == "first"


def test_binding_invalidation_can_replace_the_stale_diagnostic() -> None:
    state = RuntimeBindingState(object())
    lease = state.capture()

    state.invalidate("session replaced")

    with pytest.raises(RuntimeError, match="session replaced"):
        lease.require()
