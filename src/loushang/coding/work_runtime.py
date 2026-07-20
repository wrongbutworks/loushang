from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from loushang.coding.work_executor import (
    CodingDomainExecutor,
    CodingTurnHook,
    PromptSession,
    SubmitCodingTurn,
)
from loushang.work.event_log import EventLogBackend
from loushang.work.ports import WorkExecutionBinding
from loushang.work.runtime import WorkRuntime
from loushang.work.types import WorkOperation, WorkRun, WorkRunSpec


class CodingOperationInProgressError(RuntimeError):
    pass


class _CodingExecutionResolver:
    """Resolve prepared Coding turns while retaining a Channel payload fallback."""

    def __init__(self, session: PromptSession) -> None:
        self._session = session
        self._prepared: dict[str, CodingDomainExecutor] = {}

    def prepare(self, operation_id: str, executor: CodingDomainExecutor) -> None:
        if operation_id in self._prepared:
            raise ValueError(f"Coding operation is already prepared: {operation_id}")
        self._prepared[operation_id] = executor

    def discard(self, operation_id: str) -> None:
        self._prepared.pop(operation_id, None)

    def resolve(
        self, operation: WorkOperation, spec: WorkRunSpec
    ) -> WorkExecutionBinding:
        del spec
        executor = self._prepared.pop(operation.operation_id, None)
        if executor is None:
            executor = CodingDomainExecutor(session=self._session)
        return WorkExecutionBinding(executor=executor, cancellation=executor)


class CodingWorkRuntime:
    """Session-scoped Coding composition around the product-neutral Work runtime."""

    def __init__(
        self,
        *,
        session: PromptSession,
        event_log: EventLogBackend,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        cancellation_timeout: float | None = 30.0,
    ) -> None:
        self.session = session
        self.event_log = event_log
        self._resolver = _CodingExecutionResolver(session)
        self.work_runtime = WorkRuntime(
            resolver=self._resolver,
            event_log=event_log,
            clock=clock,
            cancellation_timeout=cancellation_timeout,
        )

    async def accept_operation(
        self,
        operation: WorkOperation,
        *,
        spec: WorkRunSpec | None = None,
        executor: CodingDomainExecutor | None = None,
    ) -> WorkRun:
        if operation.session_id is None:
            session_id = getattr(self.session, "session_id", "")
            operation = WorkOperation(
                operation_id=operation.operation_id,
                kind=operation.kind,
                session_id=session_id if isinstance(session_id, str) else "",
                domain=operation.domain,
                payload=operation.payload,
                source=operation.source,
            )
        if self.work_runtime.active_runs():
            raise CodingOperationInProgressError(
                "the active Coding session already has a Work operation"
            )
        if executor is not None:
            self._resolver.prepare(operation.operation_id, executor)
        try:
            return await self.work_runtime.accept(operation, spec=spec)
        finally:
            self._resolver.discard(operation.operation_id)

    async def submit_turn(
        self,
        turn: SubmitCodingTurn,
        *,
        session_id: str,
        operation_id: str,
        run_id: str | None = None,
    ) -> WorkRun:
        operation = turn.to_operation(
            session_id=session_id,
            operation_id=operation_id,
        )
        executor = CodingDomainExecutor(session=self.session, turn=turn)
        accepted = await self.accept_operation(
            operation,
            spec=turn.to_run_spec(run_id=run_id),
            executor=executor,
        )
        return await self.work_runtime.wait(accepted.run_id)

    async def submit_plan(
        self,
        turns: Sequence[SubmitCodingTurn],
        *,
        session_id: str,
        operation_id: str,
        run_id: str | None = None,
        before_turn: CodingTurnHook | None = None,
        after_turn: CodingTurnHook | None = None,
        wait_for_idle_after_prompt: bool = False,
    ) -> WorkRun:
        resolved_turns = tuple(turns)
        if not resolved_turns:
            raise ValueError("a Coding plan requires at least one turn")
        first = resolved_turns[0]
        if first.plan_id is None:
            raise ValueError("a Coding plan requires plan_id")
        if any(turn.plan_id != first.plan_id for turn in resolved_turns):
            raise ValueError("all Coding plan turns must share plan_id")
        operation = first.to_operation(
            session_id=session_id,
            operation_id=operation_id,
        )
        operation = WorkOperation(
            operation_id=operation.operation_id,
            kind=operation.kind,
            session_id=operation.session_id,
            domain=operation.domain,
            payload={**operation.payload, "step_count": len(resolved_turns)},
            source=operation.source,
        )
        executor = CodingDomainExecutor(
            session=self.session,
            turns=resolved_turns,
            before_turn=before_turn,
            after_turn=after_turn,
            wait_for_idle_after_prompt=wait_for_idle_after_prompt,
        )
        first_spec = first.to_run_spec(run_id=run_id)
        spec = WorkRunSpec(
            run_id=run_id,
            method_id=first.method_id,
            plan_id=first.plan_id,
            run_event_payload=first_spec.run_event_payload,
            scope_event_payload=first_spec.scope_event_payload,
            steps=tuple(turn.to_step_spec() for turn in resolved_turns),
        )
        accepted = await self.accept_operation(
            operation,
            spec=spec,
            executor=executor,
        )
        return await self.work_runtime.wait(accepted.run_id)

    async def dispose(self) -> None:
        await self.work_runtime.dispose()


__all__ = ["CodingOperationInProgressError", "CodingWorkRuntime"]
