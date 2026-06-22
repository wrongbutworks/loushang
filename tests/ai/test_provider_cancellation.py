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
