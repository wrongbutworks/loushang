from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from loushang.coding.work_executor import (
    CodingDomainExecutor,
    CodingTurnHook,
    PromptSession,
    SubmitCodingTurn,
)
from loushang.work.event_log import EventLogBackend
from loushang.work.runtime import WorkRuntime
from loushang.work.types import WorkRun, WorkRunSpec


@dataclass
class CodingWorkShell:
    """Compatibility facade from the Coding prompt API to ``WorkRuntime``."""

    session: PromptSession
    event_log: EventLogBackend
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def submit_coding_turn(
        self,
        text: str,
        *,
        session_id: str,
        images: Sequence[object] | None = None,
        method_id: str | None = None,
        plan_id: str | None = None,
        step_id: str | None = None,
        step_index: int | None = None,
        step_title: str | None = None,
        planned_constraint: Mapping[str, object] | None = None,
        audit_policy: Mapping[str, object] | None = None,
        plan_facts: Mapping[str, object] | None = None,
        step_facts: Mapping[str, object] | None = None,
        operation_id: str | None = None,
        run_id: str | None = None,
        emit_plan_start: bool = True,
        emit_plan_completion: bool = True,
        emit_plan_failure: bool = True,
    ) -> WorkRun:
        turn = SubmitCodingTurn(
            text=text,
            images=images,
            method_id=method_id,
            plan_id=plan_id,
            step_id=step_id,
            step_index=step_index,
            step_title=step_title,
            planned_constraint=planned_constraint,
            audit_policy=audit_policy,
            plan_facts=plan_facts,
            step_facts=step_facts,
            emit_plan_start=emit_plan_start,
            emit_plan_completion=emit_plan_completion,
            emit_plan_failure=emit_plan_failure,
        )
        operation = turn.to_operation(
            session_id=session_id,
            operation_id=operation_id or f"op-{uuid4().hex}",
        )
        runtime = WorkRuntime(
            executor=(executor := CodingDomainExecutor(session=self.session, turn=turn)),
            event_log=self.event_log,
            cancellation=executor,
            clock=self.clock,
        )
        accepted = await runtime.accept(
            operation,
            spec=turn.to_run_spec(run_id=run_id),
        )
        return await runtime.wait(accepted.run_id)

    async def submit_coding_plan(
        self,
        turns: Sequence[SubmitCodingTurn],
        *,
        session_id: str,
        operation_id: str | None = None,
        run_id: str | None = None,
        before_turn: CodingTurnHook | None = None,
        after_turn: CodingTurnHook | None = None,
        wait_for_idle_after_prompt: bool = False,
    ) -> WorkRun:
        """Execute all MethodPlan turns sequentially inside one Work run."""

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
            operation_id=operation_id or f"op-{uuid4().hex}",
        )
        operation_payload = dict(operation.payload)
        operation_payload["step_count"] = len(resolved_turns)
        operation = type(operation)(
            operation_id=operation.operation_id,
            kind=operation.kind,
            session_id=operation.session_id,
            domain=operation.domain,
            payload=operation_payload,
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
        runtime = WorkRuntime(
            executor=executor,
            cancellation=executor,
            event_log=self.event_log,
            clock=self.clock,
        )
        accepted = await runtime.accept(operation, spec=spec)
        return await runtime.wait(accepted.run_id)


__all__ = ["CodingWorkShell", "PromptSession"]
