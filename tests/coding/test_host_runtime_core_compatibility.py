from __future__ import annotations

import asyncio

from loushang.agent import Agent
from loushang.coding.session import RunState as CodingRunState
from loushang.coding.session.agent_session import AgentSession
from loushang.coding.session.queue_controller import (
    QueuedMessageSnapshot as CodingQueuedMessageSnapshot,
)
from loushang.coding.session.queue_controller import (
    QueueSnapshot as CodingQueueSnapshot,
)
from loushang.coding.session.session_event_bus import SessionEventBus
from loushang.coding.store import SessionManager
from loushang.harness.host.events import OrderedEventBus
from loushang.harness.host.queue import HostInputQueue
from loushang.harness.host.runtime import HostRuntime
from loushang.harness.host.types import (
    HostLifecycleEvent,
    QueuedMessageSnapshot,
    QueueSnapshot,
    RunState,
)


def test_coding_host_records_share_harness_identity() -> None:
    assert CodingRunState is RunState
    assert CodingQueueSnapshot is QueueSnapshot
    assert CodingQueuedMessageSnapshot is QueuedMessageSnapshot


def test_coding_queue_and_event_adapters_use_harness_mechanisms() -> None:
    from loushang.coding.session.queue_controller import QueueController

    controller = QueueController(
        agent=Agent(),
        preflight_user_input=lambda text: object(),
        reject_extension_command=lambda text: None,
        emit_queue_update=lambda: None,
    )

    assert isinstance(controller._queue, HostInputQueue)
    assert isinstance(SessionEventBus(), OrderedEventBus)


def test_agent_session_coordinates_public_lifecycle_through_host_runtime(
    tmp_path,
) -> None:
    async def scenario() -> None:
        agent = Agent()
        started = asyncio.Event()
        release = asyncio.Event()
        abort_calls = 0
        wait_calls = 0

        async def prompt(_input, images=None) -> None:
            del images
            started.set()
            await release.wait()

        def abort() -> None:
            nonlocal abort_calls
            abort_calls += 1
            release.set()

        async def wait_for_idle() -> None:
            nonlocal wait_calls
            wait_calls += 1

        agent.prompt = prompt  # type: ignore[method-assign]
        agent.abort = abort  # type: ignore[method-assign]
        agent.wait_for_idle = wait_for_idle  # type: ignore[method-assign]
        session = AgentSession(
            agent=agent,
            session_manager=await SessionManager.new(
                session_dir=tmp_path,
                cwd=tmp_path,
                persist=False,
            ),
        )
        host_events: list[HostLifecycleEvent] = []
        session._host_runtime.subscribe(host_events.append)

        task = asyncio.create_task(session.prompt("prepare reference output"))
        await started.wait()

        assert isinstance(session._host_runtime, HostRuntime)
        assert session.get_state().run == RunState(status="running")
        session.abort()
        await task
        await session.wait_for_idle()

        assert abort_calls == 1
        assert wait_calls == 1
        assert session.get_state().run == RunState(status="idle")
        assert [event.kind for event in host_events[:3]] == [
            "run_started",
            "abort_requested",
            "run_aborted",
        ]

        await session.dispose()
        assert session._host_runtime.is_disposed is True

    asyncio.run(scenario())
