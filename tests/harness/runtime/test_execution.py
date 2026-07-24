from __future__ import annotations

import asyncio

import pytest

from loushang.harness.events.host import HostLifecycleEvent
from loushang.harness.runtime.execution import HostRuntime, HostStateError


class ReferenceDriver:
    def __init__(self) -> None:
        self.running = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.abort_calls = 0
        self.wait_calls = 0
        self.dispose_calls = 0

    async def run(self) -> str:
        self.running = True
        self.started.set()
        try:
            await self.release.wait()
            return "reference-result"
        finally:
            self.running = False

    def abort(self) -> None:
        self.abort_calls += 1
        self.release.set()

    async def wait_for_idle(self) -> None:
        self.wait_calls += 1

    async def dispose(self) -> None:
        self.dispose_calls += 1


def _runtime(driver: ReferenceDriver) -> HostRuntime[str]:
    return HostRuntime(
        abort_driver=driver.abort,
        wait_for_idle_driver=driver.wait_for_idle,
        dispose_driver=driver.dispose,
        is_running_driver=lambda: driver.running,
    )


async def _async_value(value: str) -> str:
    return value


def test_host_runtime_runs_reference_driver_and_publishes_lifecycle() -> None:
    async def scenario() -> None:
        driver = ReferenceDriver()
        runtime = _runtime(driver)
        events: list[HostLifecycleEvent] = []
        runtime.subscribe(events.append)

        task = asyncio.create_task(runtime.run(driver.run, run_id="research-run"))
        await driver.started.wait()
        assert runtime.snapshot().status == "running"
        assert runtime.snapshot().active_run_id == "research-run"
        driver.release.set()

        assert await task == "reference-result"
        assert runtime.snapshot().status == "idle"
        assert [event.kind for event in events] == ["run_started", "run_completed"]

    asyncio.run(scenario())


def test_host_runtime_abort_delegates_and_records_aborted_completion() -> None:
    async def scenario() -> None:
        driver = ReferenceDriver()
        runtime = _runtime(driver)
        events: list[HostLifecycleEvent] = []
        runtime.subscribe(events.append)
        task = asyncio.create_task(runtime.run(driver.run, run_id="design-run"))
        await driver.started.wait()

        assert runtime.abort() is True
        assert runtime.status == "aborting"
        assert await task == "reference-result"
        await runtime.wait_for_idle()

        assert driver.abort_calls == 1
        assert driver.wait_calls == 1
        assert [event.kind for event in events] == [
            "run_started",
            "abort_requested",
            "run_aborted",
        ]

    asyncio.run(scenario())


def test_host_runtime_recovers_to_idle_after_operation_failure() -> None:
    async def scenario() -> None:
        runtime: HostRuntime[None] = HostRuntime()
        events: list[HostLifecycleEvent] = []
        runtime.subscribe(events.append)

        async def fail() -> None:
            raise ValueError("reference failure")

        with pytest.raises(ValueError, match="reference failure"):
            await runtime.run(fail)

        assert runtime.status == "idle"
        assert events[-1].kind == "run_failed"
        assert events[-1].error == "reference failure"

    asyncio.run(scenario())


def test_host_runtime_recovers_to_idle_when_start_listener_fails() -> None:
    async def scenario() -> None:
        runtime: HostRuntime[None] = HostRuntime()

        def fail_on_start(event: HostLifecycleEvent) -> None:
            if event.kind == "run_started":
                raise RuntimeError("listener failure")

        runtime.subscribe(fail_on_start)

        async def operation() -> None:
            raise AssertionError("operation must not start")

        with pytest.raises(RuntimeError, match="listener failure"):
            await runtime.run(operation)

        assert runtime.status == "idle"
        assert runtime.snapshot().active_run_id is None

    asyncio.run(scenario())


def test_host_runtime_rejects_concurrent_and_external_driver_runs() -> None:
    async def scenario() -> None:
        driver = ReferenceDriver()
        runtime = _runtime(driver)
        task = asyncio.create_task(runtime.run(driver.run))
        await driver.started.wait()
        with pytest.raises(HostStateError, match="already running"):
            await runtime.run(driver.run)
        driver.release.set()
        await task

        driver.running = True
        with pytest.raises(HostStateError, match="already running"):
            await runtime.run(driver.run)

    asyncio.run(scenario())


def test_host_runtime_runs_deferred_operation_after_active_run() -> None:
    async def scenario() -> None:
        driver = ReferenceDriver()
        runtime = _runtime(driver)
        first = asyncio.create_task(runtime.run(driver.run))
        await driver.started.wait()

        second = asyncio.create_task(
            runtime.run_after_idle(lambda: _async_value("deferred-result"))
        )
        await asyncio.sleep(0)
        assert not second.done()

        driver.release.set()
        assert await first == "reference-result"
        assert await second == "deferred-result"
        assert runtime.status == "idle"

    asyncio.run(scenario())


def test_host_runtime_coalesces_deferred_operations_by_key() -> None:
    async def scenario() -> None:
        driver = ReferenceDriver()
        runtime = _runtime(driver)
        calls: list[str] = []

        async def operation() -> str:
            calls.append("continue")
            return "continued"

        first = runtime.defer_run(operation, key="agent-continue")
        second = runtime.defer_run(operation, key="agent-continue")
        assert first is second

        assert await first == "continued"
        assert calls == ["continue"]
        assert runtime.status == "idle"

    asyncio.run(scenario())


def test_host_runtime_abort_and_wait_recovers_an_external_driver_run() -> None:
    async def scenario() -> None:
        driver = ReferenceDriver()
        driver.running = True
        runtime = _runtime(driver)

        assert runtime.status == "running"
        assert runtime.abort() is True
        assert runtime.status == "aborting"
        driver.running = False
        await runtime.wait_for_idle()

        assert runtime.status == "idle"
        assert driver.abort_calls == 1

    asyncio.run(scenario())


def test_host_runtime_disposes_idempotently_and_rejects_new_runs() -> None:
    async def scenario() -> None:
        driver = ReferenceDriver()
        runtime = _runtime(driver)
        events: list[HostLifecycleEvent] = []
        runtime.subscribe(events.append)
        task = asyncio.create_task(runtime.run(driver.run, run_id="ppt-run"))
        await driver.started.wait()

        await runtime.dispose()
        await task
        await runtime.dispose()

        assert runtime.status == "disposed"
        assert driver.abort_calls == 1
        assert driver.dispose_calls == 1
        assert events[-1].kind == "host_disposed"
        with pytest.raises(HostStateError, match="disposed"):
            await runtime.run(driver.run)

    asyncio.run(scenario())


def test_host_runtime_calls_dispose_driver_when_wait_for_idle_fails() -> None:
    async def scenario() -> None:
        dispose_calls = 0

        async def fail_wait() -> None:
            raise RuntimeError("wait failure")

        async def dispose_driver() -> None:
            nonlocal dispose_calls
            dispose_calls += 1

        runtime: HostRuntime[None] = HostRuntime(
            wait_for_idle_driver=fail_wait,
            dispose_driver=dispose_driver,
        )

        with pytest.raises(RuntimeError, match="wait failure"):
            await runtime.dispose()

        assert runtime.status == "disposed"
        assert dispose_calls == 1

    asyncio.run(scenario())
