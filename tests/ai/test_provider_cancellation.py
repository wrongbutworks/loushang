from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_is_signal_cancelled_accepts_aborted() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    assert is_signal_cancelled(SimpleNamespace(aborted=True)) is True


def test_is_signal_cancelled_accepts_cancelled() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    assert is_signal_cancelled(SimpleNamespace(cancelled=True)) is True


def test_is_signal_cancelled_accepts_asyncio_event() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    event = asyncio.Event()

    assert is_signal_cancelled(event) is False
    event.set()
    assert is_signal_cancelled(event) is True


def test_is_signal_cancelled_accepts_is_cancelled_method() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    assert is_signal_cancelled(SimpleNamespace(is_cancelled=lambda: True)) is True


def test_is_signal_cancelled_ignores_missing_or_false_flags() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    assert is_signal_cancelled(None) is False
    assert is_signal_cancelled(SimpleNamespace()) is False
    assert is_signal_cancelled(SimpleNamespace(aborted=False, cancelled=False)) is False


def test_is_signal_cancelled_treats_broken_methods_as_not_cancelled() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    def broken() -> bool:
        raise RuntimeError("boom")

    assert is_signal_cancelled(SimpleNamespace(is_cancelled=broken)) is False
    assert is_signal_cancelled(SimpleNamespace(is_set=broken)) is False


def test_wait_signal_cancelled_waits_for_asyncio_event() -> None:
    from loushang.ai.provider.cancellation import wait_signal_cancelled

    async def scenario() -> bool:
        event = asyncio.Event()
        waiter = asyncio.create_task(wait_signal_cancelled(event))
        await asyncio.sleep(0)
        blocked = not waiter.done()
        event.set()
        await asyncio.wait_for(waiter, timeout=1)
        return blocked

    assert asyncio.run(scenario()) is True


def test_wait_signal_cancelled_handles_immediate_sync_and_polled_signals() -> None:
    from loushang.ai.provider.cancellation import (
        has_cancellation_signal,
        wait_signal_cancelled,
    )

    class SyncWait:
        def __init__(self) -> None:
            self.waited = False

        def wait(self) -> None:
            self.waited = True

    class Polled:
        cancelled = False

    async def scenario() -> tuple[bool, bool, bool]:
        sync_wait = SyncWait()
        await wait_signal_cancelled(None)
        await wait_signal_cancelled(SimpleNamespace(cancelled=True))
        await wait_signal_cancelled(sync_wait)

        polled = Polled()
        waiter = asyncio.create_task(wait_signal_cancelled(polled))
        await asyncio.sleep(0)
        blocked = not waiter.done()
        polled.cancelled = True
        await asyncio.wait_for(waiter, timeout=1)
        return sync_wait.waited, blocked, has_cancellation_signal(polled)

    waited, blocked, has_signal = asyncio.run(scenario())

    assert waited is True
    assert blocked is True
    assert has_signal is True
    assert has_cancellation_signal(None) is False
