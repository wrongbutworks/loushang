from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from loushang.coding.work_executor import (
    CodingTurnHook,
    PromptSession,
    SubmitCodingTurn,
)
from loushang.coding.work_runtime import CodingWorkRuntime
from loushang.work.event_log import EventLogBackend
from loushang.work.types import WorkRun


@dataclass
class CodingWorkShell:
    """Compatibility facade from the Coding prompt API to ``WorkRuntime``."""

    session: PromptSession
    event_log: EventLogBackend
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    coding_runtime: CodingWorkRuntime | None = None

    def __post_init__(self) -> None:
        if self.coding_runtime is None:
            self.coding_runtime = CodingWorkRuntime(
                session=self.session,
                event_log=self.event_log,
                clock=self.clock,
            )

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
        )
        runtime = self._runtime()
        return await runtime.submit_turn(
            turn,
            session_id=session_id,
            operation_id=operation_id or f"op-{uuid4().hex}",
            run_id=run_id,
        )

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

        return await self._runtime().submit_plan(
            turns,
            session_id=session_id,
            operation_id=operation_id or f"op-{uuid4().hex}",
            run_id=run_id,
            before_turn=before_turn,
            after_turn=after_turn,
            wait_for_idle_after_prompt=wait_for_idle_after_prompt,
        )

    def _runtime(self) -> CodingWorkRuntime:
        runtime = self.coding_runtime
        if runtime is None:  # Populated by __post_init__; keeps narrowing explicit.
            raise RuntimeError("Coding Work runtime is not configured")
        return runtime


__all__ = ["CodingWorkShell", "PromptSession"]
