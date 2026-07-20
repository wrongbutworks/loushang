from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from loushang.coding.work_executor import (
    CodingDomainExecutor,
    PromptSession,
    SubmitCodingTurn,
)
from loushang.work.event_log import EventLogBackend
from loushang.work.runtime import WorkRuntime
from loushang.work.types import WorkRun


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
            executor=CodingDomainExecutor(session=self.session, turn=turn),
            event_log=self.event_log,
            clock=self.clock,
        )
        accepted = await runtime.accept(
            operation,
            spec=turn.to_run_spec(run_id=run_id),
        )
        return await runtime.wait(accepted.run_id)


__all__ = ["CodingWorkShell", "PromptSession"]
