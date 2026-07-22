from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar, cast

from loushang.harness.events import EventListener, OrderedEventBus
from loushang.harness.host.types import (
    HostLifecycleEvent,
    HostLifecycleEventKind,
    HostSnapshot,
    HostStatus,
)

T = TypeVar("T")
RunOperation = Callable[[], Awaitable[T]]
AbortDriver = Callable[[], None]
AsyncDriver = Callable[[], Awaitable[None] | None]
RunningProbe = Callable[[], bool]


class HostStateError(RuntimeError):
    pass


class HostRuntime(Generic[T]):
    def __init__(
        self,
        *,
        abort_driver: AbortDriver | None = None,
        wait_for_idle_driver: AsyncDriver | None = None,
        dispose_driver: AsyncDriver | None = None,
        is_running_driver: RunningProbe | None = None,
    ) -> None:
        self._abort_driver = abort_driver
        self._wait_for_idle_driver = wait_for_idle_driver
        self._dispose_driver = dispose_driver
        self._is_running_driver = is_running_driver
        self._events: OrderedEventBus[HostLifecycleEvent] = OrderedEventBus()
        self._status: HostStatus = "idle"
        self._active_run_id: str | None = None
        self._active_task: asyncio.Task[object] | None = None
        self._abort_requested = False
        self._next_run_id = 1
        self._dispose_lock = asyncio.Lock()
        self._deferred_tasks: set[asyncio.Task[object]] = set()
        self._deferred_by_key: dict[str, asyncio.Task[object]] = {}

    @property
    def status(self) -> HostStatus:
        if self._status == "idle" and self._driver_is_running():
            return "running"
        return self._status

    @property
    def is_active(self) -> bool:
        return self.status in {"running", "aborting", "disposing"}

    @property
    def is_disposed(self) -> bool:
        return self._status == "disposed"

    def snapshot(self) -> HostSnapshot:
        return HostSnapshot(
            status=self.status,
            active_run_id=self._active_run_id,
        )

    def subscribe(
        self,
        listener: EventListener[HostLifecycleEvent],
    ) -> Callable[[], None]:
        return self._events.subscribe(listener)

    async def run(
        self,
        operation: RunOperation[T],
        *,
        run_id: str | None = None,
    ) -> T:
        self._ensure_can_run()
        resolved_run_id = run_id or f"run-{self._next_run_id}"
        self._next_run_id += 1
        self._status = "running"
        self._active_run_id = resolved_run_id
        self._active_task = asyncio.current_task()
        self._abort_requested = False
        try:
            await self._publish("run_started", run_id=resolved_run_id)
        except (Exception, asyncio.CancelledError):
            self._status = "idle"
            self._active_run_id = None
            self._active_task = None
            raise

        try:
            result = await operation()
        except asyncio.CancelledError as error:
            event_kind: HostLifecycleEventKind = (
                "run_aborted" if self._abort_requested else "run_failed"
            )
            await self._finish_run(
                event_kind,
                run_id=resolved_run_id,
                error=type(error).__name__,
            )
            raise
        except Exception as error:
            await self._finish_run(
                "run_failed",
                run_id=resolved_run_id,
                error=str(error),
            )
            raise

        await self._finish_run(
            "run_aborted" if self._abort_requested else "run_completed",
            run_id=resolved_run_id,
        )
        return result

    async def run_after_idle(
        self,
        operation: RunOperation[T],
        *,
        run_id: str | None = None,
    ) -> T:
        """Run an operation once this host and its external driver are idle.

        ``run()`` intentionally rejects concurrent callers. Deferred work
        such as an automatic retry needs different semantics: it waits for the
        current run to finish, then enters ``run()`` from the same task without
        yielding between the idle check and the state transition.
        """

        current_task = asyncio.current_task()
        while True:
            active_task = self._active_task
            if active_task is current_task:
                raise HostStateError(
                    "cannot run after idle from the active host run"
                )
            if active_task is not None:
                await active_task
                continue

            if self._status in {"running", "aborting"} or self._driver_is_running():
                await self.wait_for_idle()
                continue

            # There is no await between the final idle check above and the
            # state transition performed by run(), so another asyncio task
            # cannot claim the host in between.
            return await self.run(operation, run_id=run_id)

    def defer_run(
        self,
        operation: RunOperation[T],
        *,
        key: str | None = None,
        run_id: str | None = None,
    ) -> asyncio.Task[T]:
        """Schedule one operation to run after this host becomes idle.

        The returned task is also owned by the host runtime.  A caller may
        await it for the result, but dropping it cannot create an unhandled
        background-task exception.  ``key`` coalesces equivalent deferred
        operations, such as retry and compaction requests for one continuation.
        """

        if key is not None:
            existing = self._deferred_by_key.get(key)
            if existing is not None:
                if not existing.done():
                    return cast(asyncio.Task[T], existing)
                self._deferred_by_key.pop(key, None)

        task = asyncio.create_task(self.run_after_idle(operation, run_id=run_id))
        task_object = cast(asyncio.Task[object], task)
        self._deferred_tasks.add(task_object)
        if key is not None:
            self._deferred_by_key[key] = task_object
        task.add_done_callback(self._observe_deferred_task)
        return task

    def _observe_deferred_task(self, task: asyncio.Task[object]) -> None:
        self._deferred_tasks.discard(task)
        for key, pending in tuple(self._deferred_by_key.items()):
            if pending is task:
                self._deferred_by_key.pop(key, None)
        if not task.cancelled():
            task.exception()

    def abort(self) -> bool:
        if self._status == "disposed" or not self.is_active:
            return False
        self._abort_requested = True
        if self._status in {"idle", "running"}:
            self._status = "aborting"
        if self._abort_driver is not None:
            self._abort_driver()
        self._schedule_event("abort_requested", run_id=self._active_run_id)
        return True

    async def wait_for_idle(self) -> None:
        active_task = self._active_task
        current_task = asyncio.current_task()
        if active_task is not None and active_task is current_task:
            raise HostStateError("cannot wait for idle from the active host run")
        if active_task is not None:
            await active_task
        if self._wait_for_idle_driver is not None:
            await self._await_driver(self._wait_for_idle_driver)
        if self._active_task is None and self._status in {"running", "aborting"}:
            self._status = "idle"
            self._active_run_id = None
        await self._events.drain()

    async def dispose(self) -> None:
        async with self._dispose_lock:
            if self._status == "disposed":
                return
            if self.is_active:
                self.abort()
            self._status = "disposing"
            await self._publish("host_disposing", run_id=self._active_run_id)
            try:
                try:
                    await self.wait_for_idle()
                finally:
                    if self._dispose_driver is not None:
                        await self._await_driver(self._dispose_driver)
            finally:
                self._status = "disposed"
                self._active_run_id = None
                self._active_task = None
                await self._publish("host_disposed")

    async def _finish_run(
        self,
        kind: HostLifecycleEventKind,
        *,
        run_id: str,
        error: str | None = None,
    ) -> None:
        if self._status not in {"disposing", "disposed"}:
            self._status = "idle"
        self._active_run_id = None
        self._active_task = None
        await self._publish(kind, run_id=run_id, error=error)

    def _ensure_can_run(self) -> None:
        if self._status in {"disposing", "disposed"}:
            raise HostStateError("host is disposed")
        if self.is_active:
            raise HostStateError("host is already running")

    def _driver_is_running(self) -> bool:
        return bool(
            self._is_running_driver is not None and self._is_running_driver()
        )

    async def _publish(
        self,
        kind: HostLifecycleEventKind,
        *,
        run_id: str | None = None,
        error: str | None = None,
    ) -> None:
        if not self._events.has_listeners:
            return
        await self._events.dispatch(
            HostLifecycleEvent(
                kind=kind,
                status=self._status,
                run_id=run_id,
                error=error,
            )
        )

    def _schedule_event(
        self,
        kind: HostLifecycleEventKind,
        *,
        run_id: str | None = None,
    ) -> None:
        if not self._events.has_listeners:
            return
        event = HostLifecycleEvent(
            kind=kind,
            status=self._status,
            run_id=run_id,
        )
        try:
            self._events.schedule(event)
        except RuntimeError:
            self._events.dispatch_without_loop(event)

    @staticmethod
    async def _await_driver(callback: AsyncDriver) -> None:
        result = callback()
        if inspect.isawaitable(result):
            await result
