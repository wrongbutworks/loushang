from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from loushang.work.event_log import (
    EventLogBackend,
    EventLogEntry,
    EventPosition,
)
from loushang.work.ports import WorkDomainExecutor, WorkExecutionContext
from loushang.work.types import (
    DeliveryHint,
    WorkEvent,
    WorkEventFact,
    WorkOperation,
    WorkRun,
    WorkRunSpec,
)

_LIFECYCLE_EVENT_KINDS = frozenset(
    {
        "WorkRunStarted",
        "WorkRunCancelling",
        "WorkRunCompleted",
        "WorkRunFailed",
        "WorkRunCancelled",
        "WorkPlanStarted",
        "WorkPlanCompleted",
        "WorkPlanFailed",
        "WorkPlanCancelled",
        "WorkStepStarted",
        "WorkStepCompleted",
        "WorkStepFailed",
        "WorkStepCancelled",
    }
)


class WorkRuntimeError(RuntimeError):
    pass


class UnknownWorkRunError(WorkRuntimeError):
    pass


class DuplicateWorkOperationError(WorkRuntimeError):
    pass


class WorkRunTerminalError(WorkRuntimeError):
    pass


class WorkLifecycleOwnershipError(WorkRuntimeError):
    pass


@dataclass
class _RunState:
    operation: WorkOperation
    spec: WorkRunSpec
    run: WorkRun
    sequence: int = 0
    task: asyncio.Task[None] | None = None
    error: BaseException | None = None
    terminal: bool = False


@dataclass(frozen=True)
class _ExecutionContext(WorkExecutionContext):
    runtime: WorkRuntime
    state: _RunState

    @property
    def run_id(self) -> str:
        return self.state.run.run_id

    def publish(self, fact: WorkEventFact) -> WorkEvent:
        return self.runtime._publish_domain_fact(self.state, fact)


class WorkRuntime:
    """Accept operations and own their complete observable Work lifecycle."""

    def __init__(
        self,
        *,
        executor: WorkDomainExecutor,
        event_log: EventLogBackend,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._executor = executor
        self._event_log = event_log
        self._clock = clock
        self._states: dict[str, _RunState] = {}
        self._operation_runs: dict[str, str] = {}

    async def accept(
        self,
        operation: WorkOperation,
        *,
        spec: WorkRunSpec | None = None,
    ) -> WorkRun:
        if operation.operation_id in self._operation_runs:
            raise DuplicateWorkOperationError(
                f"operation already accepted: {operation.operation_id}"
            )
        resolved_spec = spec or WorkRunSpec()
        run_id = resolved_spec.run_id or f"run-{uuid4().hex}"
        if run_id in self._states:
            raise DuplicateWorkOperationError(f"run already exists: {run_id}")
        run = WorkRun(
            run_id=run_id,
            operation_id=operation.operation_id,
            session_id=operation.session_id or "",
            domain=operation.domain,
            status="accepted",
            method_id=resolved_spec.method_id,
            plan_id=resolved_spec.plan_id,
            current_step_id=resolved_spec.step_id,
        )
        state = _RunState(operation=operation, spec=resolved_spec, run=run)
        self._append_operation(state)
        self._states[run_id] = state
        self._operation_runs[operation.operation_id] = run_id
        state.task = asyncio.create_task(
            self._execute(state), name=f"work-runtime:{run_id}"
        )
        return run

    async def wait(self, run_id: str) -> WorkRun:
        state = self._state(run_id)
        task = state.task
        if task is None:
            raise WorkRuntimeError(f"run has no execution task: {run_id}")
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await self.cancel(run_id)
            raise
        if state.error is not None:
            if isinstance(state.error, asyncio.CancelledError):
                raise asyncio.CancelledError(*state.error.args)
            raise state.error
        return state.run

    async def cancel(self, run_id: str) -> WorkRun:
        state = self._state(run_id)
        if state.terminal:
            return state.run
        if state.run.status == "accepted":
            self._start(state)
        if state.run.status == "running":
            self._begin_cancelling(state)
        task = state.task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if not state.terminal:
            self._finish_cancelled(state, asyncio.CancelledError())
        return state.run

    def get_run(self, run_id: str) -> WorkRun:
        return self._state(run_id).run

    def query(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        after: EventPosition | None = None,
        limit: int | None = None,
    ) -> list[EventLogEntry]:
        return self._event_log.query(
            run_id=run_id,
            session_id=session_id,
            after=after,
            limit=limit,
        )

    def subscribe(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        after: EventPosition | None = None,
    ) -> AsyncIterator[EventLogEntry]:
        return self._event_log.subscribe(
            run_id=run_id,
            session_id=session_id,
            after=after,
        )

    async def _execute(self, state: _RunState) -> None:
        try:
            if state.run.status == "accepted":
                self._start(state)
            await self._executor.execute(
                state.operation,
                _ExecutionContext(runtime=self, state=state),
            )
        except asyncio.CancelledError as error:
            if not state.terminal:
                if state.run.status == "accepted":
                    self._start(state)
                if state.run.status == "running":
                    self._begin_cancelling(state)
                self._finish_cancelled(state, error)
        except Exception as error:
            if not state.terminal:
                if state.run.status == "cancelling":
                    self._finish_cancelled(state, asyncio.CancelledError())
                else:
                    self._finish_failed(state, error)
        else:
            if not state.terminal:
                if state.run.status == "cancelling":
                    self._finish_cancelled(state, asyncio.CancelledError())
                else:
                    self._finish_completed(state)

    def _start(self, state: _RunState) -> None:
        if state.run.status != "accepted":
            return
        state.run = replace(state.run, status="running")
        self._publish_lifecycle(
            state,
            kind="WorkRunStarted",
            payload=state.spec.run_event_payload,
        )
        if state.spec.plan_id is not None and state.spec.emit_plan_start:
            self._publish_lifecycle(
                state,
                kind="WorkPlanStarted",
                payload=state.spec.scope_event_payload,
                delivery_hint="coalesce",
            )
        if state.spec.step_id is not None:
            self._publish_lifecycle(
                state,
                kind="WorkStepStarted",
                payload=state.spec.scope_event_payload,
                delivery_hint="coalesce",
            )

    def _begin_cancelling(self, state: _RunState) -> None:
        if state.run.status != "running":
            return
        state.run = replace(state.run, status="cancelling")
        self._publish_lifecycle(
            state,
            kind="WorkRunCancelling",
            payload=state.spec.run_event_payload,
        )

    def _finish_completed(self, state: _RunState) -> None:
        terminal_run = replace(state.run, status="completed")
        if state.spec.step_id is not None:
            self._publish_lifecycle(
                state,
                kind="WorkStepCompleted",
                payload=state.spec.scope_event_payload,
                delivery_hint="coalesce",
            )
        if state.spec.plan_id is not None and state.spec.emit_plan_completion:
            self._publish_lifecycle(
                state,
                kind="WorkPlanCompleted",
                payload=state.spec.scope_event_payload,
                delivery_hint="final_only",
            )
        state.run = terminal_run
        self._publish_terminal(
            state,
            kind="WorkRunCompleted",
            payload=state.spec.run_event_payload,
        )

    def _finish_failed(self, state: _RunState, error: Exception) -> None:
        state.error = error
        failure_payload = {**dict(state.spec.scope_event_payload), "error": str(error)}
        terminal_run = replace(state.run, status="failed")
        if state.spec.step_id is not None:
            self._publish_lifecycle(
                state,
                kind="WorkStepFailed",
                payload=failure_payload,
            )
        if state.spec.plan_id is not None and state.spec.emit_plan_failure:
            self._publish_lifecycle(
                state,
                kind="WorkPlanFailed",
                payload=failure_payload,
            )
        state.run = terminal_run
        self._publish_terminal(
            state,
            kind="WorkRunFailed",
            payload=state.spec.run_event_payload,
        )

    def _finish_cancelled(
        self, state: _RunState, error: asyncio.CancelledError
    ) -> None:
        if state.terminal:
            return
        state.error = error
        terminal_run = replace(state.run, status="cancelled")
        if state.spec.step_id is not None:
            self._publish_lifecycle(
                state,
                kind="WorkStepCancelled",
                payload=state.spec.scope_event_payload,
            )
        if state.spec.plan_id is not None:
            self._publish_lifecycle(
                state,
                kind="WorkPlanCancelled",
                payload=state.spec.scope_event_payload,
            )
        state.run = terminal_run
        self._publish_terminal(
            state,
            kind="WorkRunCancelled",
            payload=state.spec.run_event_payload,
        )

    def _publish_domain_fact(self, state: _RunState, fact: WorkEventFact) -> WorkEvent:
        if fact.kind in _LIFECYCLE_EVENT_KINDS:
            raise WorkLifecycleOwnershipError(
                f"domain executor cannot publish Work lifecycle event: {fact.kind}"
            )
        if state.terminal:
            raise WorkRunTerminalError(
                f"cannot publish event after terminal run: {state.run.run_id}"
            )
        return self._append_event(
            state,
            kind=fact.kind,
            payload=fact.payload,
            delivery_hint=fact.delivery_hint,
            source_event_ref=fact.source_event_ref,
        )

    def _publish_lifecycle(
        self,
        state: _RunState,
        *,
        kind: str,
        payload: Mapping[str, object],
        delivery_hint: DeliveryHint = "immediate",
    ) -> WorkEvent:
        if state.terminal:
            raise WorkRunTerminalError(
                f"cannot publish lifecycle after terminal run: {state.run.run_id}"
            )
        return self._append_event(
            state,
            kind=kind,
            payload=self._lifecycle_payload(state, payload),
            delivery_hint=delivery_hint,
        )

    def _publish_terminal(
        self,
        state: _RunState,
        *,
        kind: str,
        payload: Mapping[str, object],
    ) -> WorkEvent:
        if state.terminal:
            raise WorkRunTerminalError(
                f"terminal event already published: {state.run.run_id}"
            )
        event = self._append_event(
            state,
            kind=kind,
            payload=self._lifecycle_payload(state, payload),
            delivery_hint="immediate",
        )
        state.terminal = True
        return event

    def _append_operation(self, state: _RunState) -> EventPosition:
        operation = state.operation
        return self._event_log.append(
            EventLogEntry(
                entry_id=f"{state.run.run_id}-operation-0",
                entry_type="operation",
                operation_id=operation.operation_id,
                event_id=None,
                run_id=state.run.run_id,
                session_id=operation.session_id or "",
                sequence=0,
                payload={
                    "kind": operation.kind,
                    "domain": operation.domain,
                    "payload": dict(operation.payload),
                },
                created_at=self._clock(),
            )
        )

    def _append_event(
        self,
        state: _RunState,
        *,
        kind: str,
        payload: Mapping[str, object],
        delivery_hint: DeliveryHint,
        source_event_ref: str | None = None,
    ) -> WorkEvent:
        state.sequence += 1
        event = WorkEvent(
            event_id=f"{state.run.run_id}-event-{state.sequence}",
            kind=kind,
            run_id=state.run.run_id,
            session_id=state.run.session_id,
            domain=state.run.domain,
            operation_id=state.run.operation_id,
            sequence=state.sequence,
            created_at=self._clock(),
            delivery_hint=delivery_hint,
            payload=payload,
            source_event_ref=source_event_ref,
        )
        self._event_log.append(_event_log_entry(event))
        return event

    def _lifecycle_payload(
        self, state: _RunState, payload: Mapping[str, object]
    ) -> dict[str, object]:
        result = dict(payload)
        if state.run.method_id is not None:
            result["method_id"] = state.run.method_id
        if state.run.plan_id is not None:
            result["plan_id"] = state.run.plan_id
        if state.run.current_step_id is not None:
            result["step_id"] = state.run.current_step_id
        return result

    def _state(self, run_id: str) -> _RunState:
        try:
            return self._states[run_id]
        except KeyError as error:
            raise UnknownWorkRunError(f"unknown work run: {run_id}") from error


def _event_log_entry(event: WorkEvent) -> EventLogEntry:
    return EventLogEntry(
        entry_id=f"{event.run_id}-entry-{event.sequence}",
        entry_type="event",
        operation_id=event.operation_id,
        event_id=event.event_id,
        run_id=event.run_id,
        session_id=event.session_id,
        sequence=event.sequence,
        payload={
            "kind": event.kind,
            "delivery_hint": event.delivery_hint,
            "payload": dict(event.payload),
            "source_event_ref": event.source_event_ref,
        },
        created_at=event.created_at,
    )


__all__ = [
    "DuplicateWorkOperationError",
    "UnknownWorkRunError",
    "WorkLifecycleOwnershipError",
    "WorkRunTerminalError",
    "WorkRuntime",
    "WorkRuntimeError",
]
