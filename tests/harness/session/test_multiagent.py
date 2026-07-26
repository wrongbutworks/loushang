from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from loushang.harness.multiagent import (
    AgentCaller,
    AgentInputMessage,
    AgentPath,
    AgentTypeRegistry,
    AgentTypeSpec,
    HostCaller,
    MultiAgentControl,
    SubagentRoundResult,
)
from loushang.harness.multiagent.run_handle import RoundMode
from loushang.harness.runtime import HostInputQueue
from loushang.harness.runtime.execution import HostRuntime
from loushang.harness.session.multiagent import (
    AgentInputFacade,
    SessionMultiAgentRuntime,
    SessionSubagentDriver,
    SessionSubagentRequest,
    compose_multiagent_before_release,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)
HOST = HostCaller()


class _Driver:
    def __init__(self) -> None:
        self.messages: list[AgentInputMessage] = []
        self.calls: list[tuple[int, RoundMode]] = []
        self.pending: list[asyncio.Future[SubagentRoundResult]] = []
        self.abort_calls = 0
        self.dispose_calls = 0

    def deliver(self, message: AgentInputMessage) -> None:
        self.messages.append(message)

    async def run_round(
        self,
        *,
        round_id: int,
        mode: RoundMode,
    ) -> SubagentRoundResult:
        self.calls.append((round_id, mode))
        future = asyncio.get_running_loop().create_future()
        self.pending.append(future)
        return await future

    def abort(self) -> None:
        self.abort_calls += 1
        if self.pending and not self.pending[-1].done():
            self.pending[-1].set_result(
                SubagentRoundResult(
                    status="interrupted",
                    final_message="Interrupted.",
                )
            )

    async def dispose(self) -> None:
        self.dispose_calls += 1

    def complete(self, message: str = "Done.", *, summary: str | None = None) -> None:
        self.pending[-1].set_result(
            SubagentRoundResult(
                status="completed",
                final_message=message,
                summary=summary,
            )
        )


class _Factory:
    def __init__(self) -> None:
        self.drivers: dict[AgentPath, _Driver] = {}
        self.requests: list[SessionSubagentRequest] = []

    async def create_driver(self, request: SessionSubagentRequest) -> _Driver:
        self.requests.append(request)
        driver = _Driver()
        self.drivers[request.record.path] = driver
        return driver


class _FailingFactory:
    async def create_driver(
        self,
        _request: SessionSubagentRequest,
    ) -> _Driver:
        raise RuntimeError("child construction failed")


class _WorkspaceFactory:
    def __init__(self) -> None:
        self.driver = _Driver()
        self.driver.workspace_ref = "coding-worktree:reviewer"

    async def create_driver(
        self,
        _request: SessionSubagentRequest,
    ) -> _Driver:
        return self.driver


def _control() -> MultiAgentControl:
    return MultiAgentControl(
        agent_types=AgentTypeRegistry(
            (
                AgentTypeSpec(
                    name="coordinator",
                    can_spawn=True,
                    maximum_children=2,
                ),
                AgentTypeSpec(name="reviewer", maximum_children=3),
            )
        ),
        clock=lambda: NOW,
    )


async def _yield_until(predicate: Callable[[], bool]) -> None:
    for _ in range(30):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")


def test_input_facade_reuses_host_queue_and_wakes_activity_waiters() -> None:
    async def scenario() -> None:
        queue: HostInputQueue[AgentInputMessage] = HostInputQueue()
        facade = AgentInputFacade(queue=queue, build_payload=lambda message: message)
        observed = facade.activity_sequence
        waiting = asyncio.create_task(
            facade.wait_for_activity(after_sequence=observed, timeout=1)
        )
        await asyncio.sleep(0)
        message = AgentInputMessage(
            message_id="m1",
            sender=HOST,
            recipient_ref=_control().root_ref,
            kind="follow_up",
            text="Hello.",
        )

        facade.enqueue_message(message)
        outcome = await waiting

        assert queue.texts("follow_up") == ["Hello."]
        assert outcome.timed_out is False
        assert outcome.activity is not None
        assert outcome.activity.kind == "message"

    asyncio.run(scenario())


def test_input_wait_times_out_normally_and_user_steer_wakes_the_next_wait() -> None:
    async def scenario() -> None:
        queue: HostInputQueue[AgentInputMessage] = HostInputQueue()
        facade = AgentInputFacade(queue=queue, build_payload=lambda message: message)

        timed_out = await facade.wait_for_activity(timeout=0)
        observed = facade.activity_sequence
        waiting = asyncio.create_task(
            facade.wait_for_activity(after_sequence=observed, timeout=1)
        )
        await asyncio.sleep(0)
        facade.notify_steered("user-steer-1")
        steered = await waiting

        assert timed_out.timed_out is True
        assert steered.activity is not None
        assert steered.activity.kind == "steered"
        assert steered.activity.message_id == "user-steer-1"

    asyncio.run(scenario())


def test_session_driver_composes_the_existing_queue_and_host_runtime() -> None:
    async def scenario() -> None:
        queue: HostInputQueue[AgentInputMessage] = HostInputQueue()
        facade = AgentInputFacade(queue=queue, build_payload=lambda message: message)
        calls: list[tuple[int, RoundMode]] = []

        async def run_round(
            round_id: int,
            mode: RoundMode,
        ) -> SubagentRoundResult:
            calls.append((round_id, mode))
            return SubagentRoundResult(
                status="completed",
                final_message="Done.",
            )

        driver = SessionSubagentDriver(
            input_facade=facade,
            run_round=run_round,
            host_runtime=HostRuntime(),
        )
        message = AgentInputMessage(
            message_id="m1",
            sender=HOST,
            recipient_ref=_control().root_ref,
            kind="steering",
            text="Inspect this.",
        )

        driver.deliver(message)
        result = await driver.run_round(round_id=1, mode="prompt")
        await driver.dispose()

        assert queue.texts("steering") == ["Inspect this."]
        assert result.status == "completed"
        assert calls == [(1, "prompt")]

    asyncio.run(scenario())


def test_child_completion_is_queued_for_root_without_starting_a_root_turn() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _Factory()
        root_queue: HostInputQueue[AgentInputMessage] = HostInputQueue()
        root_input = AgentInputFacade(
            queue=root_queue,
            build_payload=lambda message: message,
        )
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
            root_input=root_input,
        )

        child = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="Review this.",
        )
        driver = factory.drivers[child.path]
        await _yield_until(lambda: len(driver.calls) == 1)
        driver.complete("No blockers.", summary="Looks safe")
        terminal = await runtime.await_terminal(
            caller=HOST,
            target=child.path,
        )

        assert terminal.status == "completed"
        assert driver.calls == [(1, "prompt")]
        assert root_queue.pending_count == 1
        assert "Looks safe" in root_queue.texts("follow_up")[0]
        await runtime.dispose()

    asyncio.run(scenario())


def test_child_completion_steers_an_already_running_root_turn() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _Factory()
        root_queue: HostInputQueue[AgentInputMessage] = HostInputQueue()
        root_input = AgentInputFacade(
            queue=root_queue,
            build_payload=lambda message: message,
        )
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
            root_input=root_input,
            root_is_active=lambda: True,
        )

        child = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="Review this.",
        )
        driver = factory.drivers[child.path]
        await _yield_until(lambda: len(driver.calls) == 1)
        driver.complete("No blockers.", summary="Looks safe")
        await runtime.await_terminal(caller=HOST, target=child.path)

        assert root_queue.texts("follow_up") == []
        assert "Looks safe" in root_queue.texts("steering")[0]
        await runtime.dispose()

    asyncio.run(scenario())


def test_host_can_await_the_exact_child_completion_payload() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _Factory()
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
            notice_wake_policy="discard",
        )
        child = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="Review.",
        )
        await _yield_until(lambda: bool(factory.drivers[child.path].pending))
        factory.drivers[child.path].complete(
            "Full reviewer response.",
            summary="Short summary.",
        )

        notice = await runtime.await_completion(
            caller=HOST,
            target=child.path,
            timeout=1,
        )

        assert notice.terminal.final_message == "Full reviewer response."
        assert notice.summary == "Short summary."
        await runtime.dispose()

    asyncio.run(scenario())


def test_failed_child_construction_closes_the_incarnation_and_releases_capacity() -> (
    None
):
    async def scenario() -> None:
        control = _control()
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=_FailingFactory(),
        )

        try:
            await runtime.spawn_child(
                caller=HOST,
                parent_path=AgentPath.root(),
                name="reviewer",
                agent_type="reviewer",
                initial_prompt="Review.",
            )
        except RuntimeError as error:
            assert str(error) == "child construction failed"
        else:
            raise AssertionError("spawn should fail")

        closed = control.registry.current(
            AgentPath.root().child("reviewer"),
            include_closed=True,
        )
        assert closed is not None
        assert closed.status == "closed"
        assert control.registry.open_count == 1

    asyncio.run(scenario())


def test_spawn_projects_the_product_workspace_before_the_first_round() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _WorkspaceFactory()
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
            notice_wake_policy="discard",
        )

        child = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="Review.",
        )

        assert child.workspace_ref == "coding-worktree:reviewer"
        assert [fact.kind for fact in control.facts()][:3] == [
            "spawned",
            "workspace",
            "status_changed",
        ]
        await _yield_until(lambda: bool(factory.driver.pending))
        factory.driver.complete()
        await runtime.dispose()

    asyncio.run(scenario())


def test_root_completion_wake_requires_explicit_policy_and_callback() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _Factory()
        root_queue: HostInputQueue[AgentInputMessage] = HostInputQueue()
        root_input = AgentInputFacade(
            queue=root_queue,
            build_payload=lambda message: message,
        )
        wakes = 0

        async def wake_root() -> None:
            nonlocal wakes
            wakes += 1

        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
            root_input=root_input,
            root_notice_wake=wake_root,
            notice_wake_policy="wake_if_idle",
        )
        child = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="Review.",
        )
        driver = factory.drivers[child.path]
        await _yield_until(lambda: bool(driver.pending))
        driver.complete()
        await runtime.await_terminal(caller=HOST, target=child.path)
        await runtime.drain_notice_deliveries()

        assert root_queue.pending_count == 1
        assert wakes == 1
        await runtime.dispose()

    asyncio.run(scenario())


def test_completion_notice_to_child_parent_is_queue_only_by_default() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _Factory()
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
        )
        parent = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="coordinator",
            agent_type="coordinator",
            initial_prompt="Coordinate.",
        )
        parent_driver = factory.drivers[parent.path]
        await _yield_until(lambda: len(parent_driver.calls) == 1)
        parent_driver.complete()
        await runtime.await_terminal(caller=HOST, target=parent.path)

        child = await runtime.spawn_child(
            caller=AgentCaller(parent.ref),
            parent_path=parent.path,
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="Review.",
        )
        child_driver = factory.drivers[child.path]
        await _yield_until(lambda: len(child_driver.calls) == 1)
        child_driver.complete("Finding.")
        await runtime.await_terminal(
            caller=AgentCaller(parent.ref),
            target=child.path,
        )
        await runtime.drain_notice_deliveries()

        assert len(parent_driver.calls) == 1
        assert parent_driver.messages[-1].message_id.startswith("completion:")
        await runtime.dispose()

    asyncio.run(scenario())


def test_follow_up_after_terminal_uses_the_same_tracked_handle() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _Factory()
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
        )
        child = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="First.",
        )
        driver = factory.drivers[child.path]
        await _yield_until(lambda: len(driver.calls) == 1)
        driver.complete("First done.")
        await runtime.await_terminal(caller=HOST, target=child.path)

        delivery = await runtime.send_message(
            caller=HOST,
            target=child.path,
            text="Second.",
        )
        await _yield_until(lambda: len(driver.calls) == 2)
        driver.complete("Second done.")
        terminal = await runtime.await_terminal(caller=HOST, target=child.path)

        assert delivery.triggered_new_round is True
        assert driver.calls == [(1, "prompt"), (2, "continue")]
        assert terminal.round_id == 2
        await runtime.dispose()

    asyncio.run(scenario())


def test_recursive_close_interrupts_and_disposes_deepest_first() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _Factory()
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
        )
        parent = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="coordinator",
            agent_type="coordinator",
            initial_prompt="Coordinate.",
        )
        child = await runtime.spawn_child(
            caller=AgentCaller(parent.ref),
            parent_path=parent.path,
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="Review.",
        )
        await _yield_until(
            lambda: all(
                factory.drivers[path].pending for path in (parent.path, child.path)
            )
        )

        result = await runtime.close_agent(caller=HOST, target=parent.path)

        assert [record.path for record in result.closed] == [
            child.path,
            parent.path,
        ]
        assert factory.drivers[child.path].dispose_calls == 1
        assert factory.drivers[parent.path].dispose_calls == 1
        assert control.registry.get(control.root_ref).status == "idle"

    asyncio.run(scenario())


def test_before_release_hook_closes_children_then_calls_existing_hook() -> None:
    async def scenario() -> None:
        control = _control()
        factory = _Factory()
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
        )
        child = await runtime.spawn_child(
            caller=HOST,
            parent_path=AgentPath.root(),
            name="reviewer",
            agent_type="reviewer",
            initial_prompt="Review.",
        )
        await _yield_until(lambda: bool(factory.drivers[child.path].pending))
        order: list[str] = []

        async def existing(
            _session: object,
            _target: object | None,
            _transition: object,
        ) -> None:
            assert (
                control.registry.get(child.ref, include_closed=True).status == "closed"
            )
            order.append("existing")

        hook = compose_multiagent_before_release(
            resolve_runtime=lambda _session: runtime,
            existing=existing,
        )
        await hook(object(), None, object())

        assert order == ["existing"]
        assert factory.drivers[child.path].dispose_calls == 1

    asyncio.run(scenario())
