from __future__ import annotations

import asyncio

from loushang.harness.runtime import CoalescingScheduler


def test_scheduler_runs_immediately_without_an_event_loop() -> None:
    calls: list[set[str]] = []
    scheduler = CoalescingScheduler[set[str]](
        calls.append,
        merge=lambda left, right: left | right,
    )

    scheduler.schedule({"project"})

    assert calls == [{"project"}]
    assert scheduler.is_pending is False


def test_scheduler_coalesces_requests_during_the_delay() -> None:
    calls: list[set[str]] = []
    scheduler = CoalescingScheduler[set[str]](
        calls.append,
        merge=lambda left, right: left | right,
        delay_seconds=0.01,
    )

    async def scenario() -> None:
        scheduler.schedule({"project"})
        scheduler.schedule({"global"})
        await asyncio.sleep(0.02)

    asyncio.run(scenario())

    assert calls == [{"project", "global"}]


def test_scheduler_drain_cancels_the_delay_and_runs_pending_work() -> None:
    calls: list[bool] = []
    scheduler = CoalescingScheduler[bool](
        calls.append,
        merge=lambda left, right: left or right,
        delay_seconds=60.0,
    )

    async def scenario() -> None:
        scheduler.schedule(False)
        scheduler.schedule(True)
        await scheduler.drain()

    asyncio.run(scenario())

    assert calls == [True]
    assert scheduler.is_pending is False


def test_scheduler_awaits_async_callbacks() -> None:
    calls: list[str] = []

    async def callback(value: str) -> None:
        await asyncio.sleep(0)
        calls.append(value)

    scheduler = CoalescingScheduler(
        callback,
        merge=lambda left, right: f"{left},{right}",
    )

    scheduler.schedule("research")

    assert calls == ["research"]
