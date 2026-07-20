from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime


def _operation():
    from loushang.work import WorkOperation

    return WorkOperation(
        operation_id="op-1",
        kind="TestOperation",
        session_id="session-1",
        domain="test",
        payload={"input": "hello"},
    )


def _spec():
    from loushang.work import WorkRunSpec

    return WorkRunSpec(
        run_id="run-1",
        method_id="method-1",
        plan_id="plan-1",
        step_id="step-1",
        run_event_payload={"source_type": "test"},
        scope_event_payload={"step_index": 0, "step_title": "Test step"},
    )


def _clock():
    return datetime(2026, 7, 20, 10, 0, tzinfo=UTC)


@dataclass
class _ControlledExecutor:
    started: asyncio.Event
    release: asyncio.Event
    context: object | None = None

    async def execute(self, operation, context):
        from loushang.work import WorkEventFact

        self.context = context
        context.publish(
            WorkEventFact(
                kind="DomainFact",
                payload={"operation_kind": operation.kind},
                source_event_ref="source-1",
            )
        )
        self.started.set()
        await self.release.wait()
        return {"ok": True}


def test_work_runtime_accepts_runs_and_owns_success_lifecycle() -> None:
    from loushang.work import InMemoryEventLogBackend, WorkEventFact, WorkRuntime

    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        executor = _ControlledExecutor(started=started, release=release)
        runtime = WorkRuntime(
            executor=executor,
            event_log=InMemoryEventLogBackend(),
            clock=_clock,
        )

        accepted = await runtime.accept(_operation(), spec=_spec())

        assert accepted.status == "accepted"
        assert runtime.get_run("run-1").status == "accepted"
        assert [entry.payload["kind"] for entry in runtime.query(run_id="run-1")] == [
            "TestOperation"
        ]

        await started.wait()
        assert runtime.get_run("run-1").status == "running"
        release.set()
        completed = await runtime.wait("run-1")

        assert completed.status == "completed"
        entries = runtime.query(run_id="run-1")
        assert [entry.sequence for entry in entries] == list(range(len(entries)))
        assert [entry.payload["kind"] for entry in entries] == [
            "TestOperation",
            "WorkRunStarted",
            "WorkPlanStarted",
            "WorkStepStarted",
            "DomainFact",
            "WorkStepCompleted",
            "WorkPlanCompleted",
            "WorkRunCompleted",
        ]
        assert entries[4].payload["source_event_ref"] == "source-1"
        assert entries[-1].payload["payload"] == {
            "source_type": "test",
            "method_id": "method-1",
            "plan_id": "plan-1",
            "step_id": "step-1",
        }

        assert executor.context is not None
        try:
            executor.context.publish(WorkEventFact(kind="LateFact", payload={}))
        except Exception as error:
            assert type(error).__name__ == "WorkRunTerminalError"
        else:
            raise AssertionError("expected terminal event rejection")
        assert runtime.query(run_id="run-1") == entries

    asyncio.run(scenario())


def test_work_runtime_orders_step_plan_and_run_failure_and_reraises() -> None:
    from loushang.work import InMemoryEventLogBackend, WorkRuntime

    class FailingExecutor:
        async def execute(self, operation, context):
            del operation, context
            raise RuntimeError("domain failed")

    async def scenario() -> None:
        runtime = WorkRuntime(
            executor=FailingExecutor(),
            event_log=InMemoryEventLogBackend(),
            clock=_clock,
        )
        await runtime.accept(_operation(), spec=_spec())

        try:
            await runtime.wait("run-1")
        except RuntimeError as error:
            assert str(error) == "domain failed"
        else:
            raise AssertionError("expected domain failure")

        assert runtime.get_run("run-1").status == "failed"
        entries = runtime.query(run_id="run-1")
        assert [entry.payload["kind"] for entry in entries][-3:] == [
            "WorkStepFailed",
            "WorkPlanFailed",
            "WorkRunFailed",
        ]
        assert entries[-3].payload["payload"]["error"] == "domain failed"
        assert (
            sum(
                entry.payload["kind"]
                in {"WorkRunCompleted", "WorkRunFailed", "WorkRunCancelled"}
                for entry in entries
            )
            == 1
        )

    asyncio.run(scenario())


def test_work_runtime_cancel_transitions_and_terminal_order_are_deterministic() -> None:
    from loushang.work import InMemoryEventLogBackend, WorkRuntime

    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        runtime = WorkRuntime(
            executor=_ControlledExecutor(started=started, release=release),
            event_log=InMemoryEventLogBackend(),
            clock=_clock,
        )
        await runtime.accept(_operation(), spec=_spec())
        await started.wait()

        cancelled = await runtime.cancel("run-1")

        assert cancelled.status == "cancelled"
        assert [entry.payload["kind"] for entry in runtime.query(run_id="run-1")][
            -4:
        ] == [
            "WorkRunCancelling",
            "WorkStepCancelled",
            "WorkPlanCancelled",
            "WorkRunCancelled",
        ]
        try:
            await runtime.wait("run-1")
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("expected cancellation")

        entries = runtime.query(run_id="run-1")
        assert entries[-1].payload["kind"] == "WorkRunCancelled"
        assert (
            sum(entry.payload["kind"] == "WorkRunCancelled" for entry in entries) == 1
        )

    asyncio.run(scenario())


def test_work_runtime_cancel_before_executor_starts_still_follows_full_state_path() -> (
    None
):
    from loushang.work import InMemoryEventLogBackend, WorkRuntime

    async def scenario() -> None:
        runtime = WorkRuntime(
            executor=_ControlledExecutor(
                started=asyncio.Event(), release=asyncio.Event()
            ),
            event_log=InMemoryEventLogBackend(),
            clock=_clock,
        )
        await runtime.accept(_operation(), spec=_spec())

        cancelled = await runtime.cancel("run-1")

        assert cancelled.status == "cancelled"
        assert [entry.payload["kind"] for entry in runtime.query(run_id="run-1")] == [
            "TestOperation",
            "WorkRunStarted",
            "WorkPlanStarted",
            "WorkStepStarted",
            "WorkRunCancelling",
            "WorkStepCancelled",
            "WorkPlanCancelled",
            "WorkRunCancelled",
        ]

    asyncio.run(scenario())


def test_executor_cancelled_error_is_a_cancelled_run_not_a_failure() -> None:
    from loushang.work import InMemoryEventLogBackend, WorkRuntime

    class CancelledExecutor:
        async def execute(self, operation, context):
            del operation, context
            raise asyncio.CancelledError("executor cancelled")

    async def scenario() -> None:
        runtime = WorkRuntime(
            executor=CancelledExecutor(),
            event_log=InMemoryEventLogBackend(),
            clock=_clock,
        )
        await runtime.accept(_operation(), spec=_spec())

        try:
            await runtime.wait("run-1")
        except asyncio.CancelledError as error:
            assert error.args == ("executor cancelled",)
        else:
            raise AssertionError("expected cancellation")

        kinds = [entry.payload["kind"] for entry in runtime.query(run_id="run-1")]
        assert "WorkRunFailed" not in kinds
        assert kinds[-4:] == [
            "WorkRunCancelling",
            "WorkStepCancelled",
            "WorkPlanCancelled",
            "WorkRunCancelled",
        ]

    asyncio.run(scenario())


def test_domain_executor_cannot_publish_work_lifecycle_events() -> None:
    from loushang.work import InMemoryEventLogBackend, WorkEventFact, WorkRuntime

    class InvalidExecutor:
        async def execute(self, operation, context):
            del operation
            context.publish(WorkEventFact(kind="WorkRunCompleted", payload={}))

    async def scenario() -> None:
        runtime = WorkRuntime(
            executor=InvalidExecutor(),
            event_log=InMemoryEventLogBackend(),
            clock=_clock,
        )
        await runtime.accept(_operation(), spec=_spec())

        try:
            await runtime.wait("run-1")
        except Exception as error:
            assert type(error).__name__ == "WorkLifecycleOwnershipError"
        else:
            raise AssertionError("expected lifecycle ownership failure")

        kinds = [entry.payload["kind"] for entry in runtime.query(run_id="run-1")]
        assert kinds.count("WorkRunCompleted") == 0
        assert kinds[-1] == "WorkRunFailed"

    asyncio.run(scenario())


def test_work_runtime_subscribe_replays_and_streams_runtime_owned_log() -> None:
    from loushang.work import InMemoryEventLogBackend, WorkRuntime

    class ImmediateExecutor:
        async def execute(self, operation, context):
            del operation, context
            return None

    async def scenario() -> None:
        runtime = WorkRuntime(
            executor=ImmediateExecutor(),
            event_log=InMemoryEventLogBackend(),
            clock=_clock,
        )
        accepted = await runtime.accept(_operation(), spec=_spec())
        stream = runtime.subscribe(run_id=accepted.run_id)

        operation_entry = await asyncio.wait_for(anext(stream), timeout=0.1)
        assert operation_entry.payload["kind"] == "TestOperation"
        await runtime.wait(accepted.run_id)

        streamed = [
            await asyncio.wait_for(anext(stream), timeout=0.1) for _ in range(6)
        ]
        assert streamed[-1].payload["kind"] == "WorkRunCompleted"
        await stream.aclose()

    asyncio.run(scenario())


def test_work_runtime_allocates_unique_run_ids_and_rejects_duplicate_operations() -> (
    None
):
    from loushang.work import InMemoryEventLogBackend, WorkOperation, WorkRuntime
    from loushang.work.runtime import DuplicateWorkOperationError

    class ImmediateExecutor:
        async def execute(self, operation, context):
            del operation, context
            return None

    async def scenario() -> None:
        runtime = WorkRuntime(
            executor=ImmediateExecutor(),
            event_log=InMemoryEventLogBackend(),
            clock=_clock,
        )
        first_operation = _operation()
        second_operation = WorkOperation(
            operation_id="op-2",
            kind="TestOperation",
            session_id="session-1",
            domain="test",
            payload={},
        )

        first = await runtime.accept(first_operation)
        second = await runtime.accept(second_operation)

        assert first.run_id.startswith("run-")
        assert second.run_id.startswith("run-")
        assert first.run_id != second.run_id
        await runtime.wait(first.run_id)
        await runtime.wait(second.run_id)
        try:
            await runtime.accept(first_operation)
        except DuplicateWorkOperationError:
            pass
        else:
            raise AssertionError("expected duplicate operation rejection")

    asyncio.run(scenario())
