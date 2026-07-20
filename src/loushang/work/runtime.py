from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from loushang.work.event_log import EventLogBackend, EventLogEntry, EventPosition
from loushang.work.ports import (
    WorkDomainCancellation,
    WorkDomainExecutor,
    WorkExecutionContext,
)
from loushang.work.types import (
    DeliveryHint,
    WorkEvent,
    WorkEventFact,
    WorkOperation,
    WorkRun,
    WorkRunSpec,
    WorkStepSpec,
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
    cancellation_task: asyncio.Task[object] | None = None
    error: BaseException | None = None
    terminal: bool = False
    current_step: WorkStepSpec | None = None
    current_step_index: int | None = None
    step_active: bool = False


@dataclass(frozen=True)
class _ExecutionContext(WorkExecutionContext):
    runtime: WorkRuntime
    state: _RunState

    @property
    def run_id(self) -> str:
        return self.state.run.run_id

    @property
    def step_id(self) -> str | None:
        step = self.state.current_step
        return step.step_id if step is not None else None

    @property
    def step_index(self) -> int | None:
        return self.state.current_step_index

    @property
    def step_payload(self) -> Mapping[str, object]:
        step = self.state.current_step
        return step.payload if step is not None else {}

    def publish(self, fact: WorkEventFact) -> WorkEvent:
        return self.runtime._publish_domain_fact(self.state, fact)


WorkEventListener = Callable[[WorkEvent], None]


class WorkRuntime:
    """Accept operations and own their complete observable Work lifecycle."""

    def __init__(
        self,
        *,
        executor: WorkDomainExecutor,
        event_log: EventLogBackend,
        cancellation: WorkDomainCancellation | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._executor = executor
        self._cancellation = cancellation
        self._event_log = event_log
        self._clock = clock
        self._states: dict[str, _RunState] = {}
        self._operation_runs: dict[str, str] = {}
        self._event_listeners: list[WorkEventListener] = []

    async def accept(
        self,
        operation: WorkOperation,
        *,
        spec: WorkRunSpec | None = None,
    ) -> WorkRun:
        if self.get_run_for_operation(operation.operation_id) is not None:
            raise DuplicateWorkOperationError(
                f"operation already accepted: {operation.operation_id}"
            )
        resolved_spec = spec or WorkRunSpec()
        _validate_spec(resolved_spec)
        run_id = resolved_spec.run_id or f"run-{uuid4().hex}"
        if self._find_run(run_id) is not None:
            raise DuplicateWorkOperationError(f"run already exists: {run_id}")
        steps = _steps(resolved_spec)
        first_step_id = steps[0].step_id if steps else None
        run = WorkRun(
            run_id=run_id,
            operation_id=operation.operation_id,
            session_id=operation.session_id or "",
            domain=operation.domain,
            status="accepted",
            method_id=resolved_spec.method_id,
            plan_id=resolved_spec.plan_id,
            current_step_id=first_step_id,
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
            self._activate_first_step(state)
        if state.run.status == "running":
            self._begin_cancelling(state)

        cancellation_error: BaseException | None = None
        cancellation_settled = False
        if self._cancellation is not None:
            if state.cancellation_task is None:
                state.cancellation_task = asyncio.create_task(
                    self._cancellation.cancel_and_wait(
                        state.operation,
                        _ExecutionContext(runtime=self, state=state),
                    ),
                    name=f"work-cancel:{run_id}",
                )
            try:
                cancellation_result = await asyncio.shield(state.cancellation_task)
                cancellation_settled = cancellation_result is not False
            except BaseException as error:
                cancellation_error = error

        task = state.task
        if task is not None and not task.done():
            if (
                self._cancellation is None
                or not cancellation_settled
                or cancellation_error is not None
            ):
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if not state.terminal:
            self._finish_cancelled(state, asyncio.CancelledError())
        if cancellation_error is not None:
            raise cancellation_error
        return state.run

    def get_run(self, run_id: str) -> WorkRun:
        run = self._find_run(run_id)
        if run is None:
            raise UnknownWorkRunError(f"unknown work run: {run_id}")
        return run

    def get_run_for_operation(self, operation_id: str) -> WorkRun | None:
        run_id = self._operation_runs.get(operation_id)
        if run_id is not None:
            return self._states[run_id].run
        from loushang.work.run_projection import project_work_runs

        return next(
            (
                run
                for run in project_work_runs(self._event_log.query())
                if run.operation_id == operation_id
            ),
            None,
        )

    def active_runs(self, *, session_id: str | None = None) -> tuple[WorkRun, ...]:
        return tuple(
            state.run
            for state in self._states.values()
            if not state.terminal
            and (session_id is None or state.run.session_id == session_id)
        )

    def query_runs(
        self, *, run_id: str | None = None, session_id: str | None = None
    ) -> tuple[WorkRun, ...]:
        from loushang.work.run_projection import project_work_runs

        return project_work_runs(
            self._event_log.query(run_id=run_id, session_id=session_id)
        )

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

    def subscribe_events(self, listener: WorkEventListener) -> Callable[[], None]:
        self._event_listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

        return unsubscribe

    async def dispose(self) -> None:
        """Cancel and settle every active run owned by this runtime."""

        for run in tuple(self.active_runs()):
            with suppress(BaseException):
                await self.cancel(run.run_id)

    async def _execute(self, state: _RunState) -> None:
        try:
            if state.run.status == "accepted":
                self._start(state)
            steps = _steps(state.spec)
            if not steps:
                await self._executor.execute(
                    state.operation,
                    _ExecutionContext(runtime=self, state=state),
                )
            else:
                for index, step in enumerate(steps):
                    if state.run.status == "cancelling":
                        raise asyncio.CancelledError()
                    self._start_step(state, step, index)
                    await self._executor.execute(
                        state.operation,
                        _ExecutionContext(runtime=self, state=state),
                    )
                    self._complete_step(state)
        except asyncio.CancelledError as error:
            if not state.terminal:
                if state.run.status == "accepted":
                    self._start(state)
                    self._activate_first_step(state)
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
                    cancellation_task = state.cancellation_task
                    if cancellation_task is not None:
                        with suppress(BaseException):
                            await asyncio.shield(cancellation_task)
                    self._finish_cancelled(state, asyncio.CancelledError())
                else:
                    self._finish_completed(state)

    def _start(self, state: _RunState) -> None:
        if state.run.status != "accepted":
            return
        state.run = replace(state.run, status="running")
        self._publish_lifecycle(
            state, kind="WorkRunStarted", payload=state.spec.run_event_payload
        )
        if state.spec.plan_id is not None and state.spec.emit_plan_start:
            self._publish_lifecycle(
                state,
                kind="WorkPlanStarted",
                payload=state.spec.scope_event_payload,
                delivery_hint="coalesce",
            )

    def _activate_first_step(self, state: _RunState) -> None:
        steps = _steps(state.spec)
        if steps and not state.step_active:
            self._start_step(state, steps[0], 0)

    def _start_step(
        self, state: _RunState, step: WorkStepSpec, index: int
    ) -> None:
        if state.step_active:
            if state.current_step == step and state.current_step_index == index:
                return
            raise WorkRuntimeError("cannot start a Work step before the prior step ends")
        state.current_step = step
        state.current_step_index = index
        state.step_active = True
        state.run = replace(state.run, current_step_id=step.step_id)
        self._publish_lifecycle(
            state,
            kind="WorkStepStarted",
            payload=_step_payload(state, step),
            delivery_hint="coalesce",
        )

    def _complete_step(self, state: _RunState) -> None:
        if not state.step_active or state.current_step is None:
            return
        self._publish_lifecycle(
            state,
            kind="WorkStepCompleted",
            payload=_step_payload(state, state.current_step),
            delivery_hint="coalesce",
        )
        state.step_active = False

    def _begin_cancelling(self, state: _RunState) -> None:
        if state.run.status != "running":
            return
        state.run = replace(state.run, status="cancelling")
        self._publish_lifecycle(
            state, kind="WorkRunCancelling", payload=state.spec.run_event_payload
        )

    def _finish_completed(self, state: _RunState) -> None:
        terminal_run = replace(state.run, status="completed")
        if state.spec.plan_id is not None and state.spec.emit_plan_completion:
            self._publish_lifecycle(
                state,
                kind="WorkPlanCompleted",
                payload=state.spec.scope_event_payload,
                delivery_hint="final_only",
            )
        state.run = terminal_run
        self._publish_terminal(
            state, kind="WorkRunCompleted", payload=state.spec.run_event_payload
        )

    def _finish_failed(self, state: _RunState, error: Exception) -> None:
        state.error = error
        failure_payload = {**self._current_scope_payload(state), "error": str(error)}
        terminal_run = replace(state.run, status="failed")
        if state.step_active:
            self._publish_lifecycle(state, kind="WorkStepFailed", payload=failure_payload)
            state.step_active = False
        if state.spec.plan_id is not None and state.spec.emit_plan_failure:
            self._publish_lifecycle(state, kind="WorkPlanFailed", payload=failure_payload)
        state.run = terminal_run
        self._publish_terminal(
            state, kind="WorkRunFailed", payload=state.spec.run_event_payload
        )

    def _finish_cancelled(
        self, state: _RunState, error: asyncio.CancelledError
    ) -> None:
        if state.terminal:
            return
        state.error = error
        terminal_run = replace(state.run, status="cancelled")
        if state.step_active:
            self._publish_lifecycle(
                state,
                kind="WorkStepCancelled",
                payload=self._current_scope_payload(state),
            )
            state.step_active = False
        if state.spec.plan_id is not None:
            self._publish_lifecycle(
                state,
                kind="WorkPlanCancelled",
                payload=self._current_scope_payload(state),
            )
        state.run = terminal_run
        self._publish_terminal(
            state, kind="WorkRunCancelled", payload=state.spec.run_event_payload
        )

    def _current_scope_payload(self, state: _RunState) -> dict[str, object]:
        if state.current_step is not None:
            return _step_payload(state, state.current_step)
        return dict(state.spec.scope_event_payload)

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
        self, state: _RunState, *, kind: str, payload: Mapping[str, object]
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
        for listener in tuple(self._event_listeners):
            with suppress(Exception):
                listener(event)
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
            raise UnknownWorkRunError(f"unknown active work run: {run_id}") from error

    def _find_run(self, run_id: str) -> WorkRun | None:
        state = self._states.get(run_id)
        if state is not None:
            return state.run
        return next(iter(self.query_runs(run_id=run_id)), None)


def _steps(spec: WorkRunSpec) -> tuple[WorkStepSpec, ...]:
    if spec.steps:
        return spec.steps
    if spec.step_id is None:
        return ()
    return (WorkStepSpec(step_id=spec.step_id, payload=spec.scope_event_payload),)


def _validate_spec(spec: WorkRunSpec) -> None:
    step_ids = [step.step_id for step in spec.steps]
    if any(not step_id for step_id in step_ids):
        raise ValueError("Work step_id must be non-empty")
    if len(set(step_ids)) != len(step_ids):
        raise ValueError("Work step_id values must be unique within a run")
    if spec.steps and spec.plan_id is None:
        raise ValueError("multi-step Work runs require plan_id")


def _step_payload(state: _RunState, step: WorkStepSpec) -> dict[str, object]:
    result = dict(state.spec.scope_event_payload)
    result.update(step.payload)
    if state.current_step_index is not None:
        result.setdefault("step_index", state.current_step_index)
    return result


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
