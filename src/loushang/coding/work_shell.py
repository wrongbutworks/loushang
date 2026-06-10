from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from loushang.work.event_log import EventLogBackend, EventLogEntry
from loushang.work.projection import (
    WorkEventProjectionContext,
    project_agent_event_to_work_events,
)
from loushang.work.types import WorkEvent, WorkOperation, WorkRun

SessionEventListener = Callable[[Mapping[str, object]], Awaitable[None] | None]


class PromptSession(Protocol):
    def subscribe(self, listener: SessionEventListener) -> Callable[[], None]: ...

    def prompt(self, text: str, *, images: Sequence[object] | None = None) -> Awaitable[None]: ...


@dataclass
class CodingWorkShell:
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
        operation_id = operation_id or f"op-{uuid4().hex}"
        run_id = run_id or f"run-{uuid4().hex}"
        sequence = 0
        operation = WorkOperation(
            operation_id=operation_id,
            kind="SubmitCodingTurn",
            session_id=session_id,
            domain="coding",
            payload=_operation_payload(
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
            ),
        )
        self._append_operation(operation, run_id=run_id, sequence=sequence)

        run = WorkRun(
            run_id=run_id,
            operation_id=operation_id,
            session_id=session_id,
            domain="coding",
            status="running",
            method_id=method_id,
            plan_id=plan_id,
            current_step_id=step_id,
        )
        sequence += 1
        self._append_event(
            _work_event(
                kind="WorkRunStarted",
                run=run,
                sequence=sequence,
                created_at=self.clock(),
                payload={"source_type": "work_shell"},
            ),
        )
        if plan_id is not None and emit_plan_start:
            sequence += 1
            self._append_event(
                _work_event(
                    kind="WorkPlanStarted",
                    run=run,
                    sequence=sequence,
                    created_at=self.clock(),
                    delivery_hint="coalesce",
                    payload=_step_payload(
                        step_index=step_index,
                        step_title=step_title,
                        planned_constraint=planned_constraint,
                        audit_policy=audit_policy,
                        plan_facts=plan_facts,
                        step_facts=step_facts,
                    ),
                ),
            )
        if step_id is not None:
            sequence += 1
            self._append_event(
                _work_event(
                    kind="WorkStepStarted",
                    run=run,
                    sequence=sequence,
                    created_at=self.clock(),
                    delivery_hint="coalesce",
                    payload=_step_payload(
                        step_index=step_index,
                        step_title=step_title,
                        planned_constraint=planned_constraint,
                        audit_policy=audit_policy,
                        plan_facts=plan_facts,
                        step_facts=step_facts,
                    ),
                ),
            )

        async def listener(event: Mapping[str, object]) -> None:
            nonlocal sequence
            sequence += 1
            context = WorkEventProjectionContext(
                run_id=run_id,
                session_id=session_id,
                domain="coding",
                operation_id=operation_id,
                sequence=sequence,
                created_at=self.clock(),
                event_id_prefix=f"{run_id}-event",
            )
            for work_event in project_agent_event_to_work_events(event, context=context):
                self._append_event(work_event)

        unsubscribe = self.session.subscribe(listener)
        try:
            if images is None:
                await self.session.prompt(text)
            else:
                await self.session.prompt(text, images=images)
        except Exception as error:
            sequence += 1
            failed_run = WorkRun(
                run_id=run_id,
                operation_id=operation_id,
                session_id=session_id,
                domain="coding",
                status="failed",
                method_id=method_id,
                plan_id=plan_id,
                current_step_id=step_id,
            )
            failure_payload = _step_payload(
                step_index=step_index,
                step_title=step_title,
                planned_constraint=planned_constraint,
                audit_policy=audit_policy,
                plan_facts=plan_facts,
                step_facts=step_facts,
                error=error,
            )
            if step_id is not None:
                self._append_event(
                    _work_event(
                        kind="WorkStepFailed",
                        run=failed_run,
                        sequence=sequence,
                        created_at=self.clock(),
                        delivery_hint="immediate",
                        payload=failure_payload,
                    ),
                )
                sequence += 1
            if plan_id is not None and emit_plan_failure:
                self._append_event(
                    _work_event(
                        kind="WorkPlanFailed",
                        run=failed_run,
                        sequence=sequence,
                        created_at=self.clock(),
                        delivery_hint="immediate",
                        payload=failure_payload,
                    ),
                )
                sequence += 1
            self._append_event(
                _work_event(
                    kind="WorkRunFailed",
                    run=failed_run,
                    sequence=sequence,
                    created_at=self.clock(),
                    payload={"source_type": "work_shell"},
                ),
            )
            raise
        finally:
            unsubscribe()

        sequence += 1
        completed_run = WorkRun(
            run_id=run_id,
            operation_id=operation_id,
            session_id=session_id,
            domain="coding",
            status="completed",
            method_id=method_id,
            plan_id=plan_id,
            current_step_id=step_id,
        )
        if step_id is not None:
            self._append_event(
                _work_event(
                    kind="WorkStepCompleted",
                    run=completed_run,
                    sequence=sequence,
                    created_at=self.clock(),
                    delivery_hint="coalesce",
                    payload=_step_payload(
                        step_index=step_index,
                        step_title=step_title,
                        planned_constraint=planned_constraint,
                        audit_policy=audit_policy,
                        plan_facts=plan_facts,
                        step_facts=step_facts,
                    ),
                ),
            )
            sequence += 1
        if plan_id is not None and emit_plan_completion:
            self._append_event(
                _work_event(
                    kind="WorkPlanCompleted",
                    run=completed_run,
                    sequence=sequence,
                    created_at=self.clock(),
                    delivery_hint="final_only",
                    payload=_step_payload(
                        step_index=step_index,
                        step_title=step_title,
                        planned_constraint=planned_constraint,
                        audit_policy=audit_policy,
                        plan_facts=plan_facts,
                        step_facts=step_facts,
                    ),
                ),
            )
            sequence += 1
        self._append_event(
            _work_event(
                kind="WorkRunCompleted",
                run=completed_run,
                sequence=sequence,
                created_at=self.clock(),
                payload={"source_type": "work_shell"},
            ),
        )
        return completed_run

    def _append_operation(self, operation: WorkOperation, *, run_id: str, sequence: int) -> None:
        self.event_log.append(
            EventLogEntry(
                entry_id=f"{run_id}-operation-{sequence}",
                entry_type="operation",
                operation_id=operation.operation_id,
                event_id=None,
                run_id=run_id,
                session_id=operation.session_id or "",
                sequence=sequence,
                payload={
                    "kind": operation.kind,
                    "domain": operation.domain,
                    "payload": dict(operation.payload),
                },
                created_at=self.clock(),
            ),
        )

    def _append_event(self, event: WorkEvent) -> None:
        self.event_log.append(_event_log_entry_from_work_event(event))


def _work_event(
    *,
    kind: str,
    run: WorkRun,
    sequence: int,
    created_at: datetime,
    payload: Mapping[str, object],
    delivery_hint: str = "immediate",
) -> WorkEvent:
    event_payload = dict(payload)
    if run.method_id is not None:
        event_payload["method_id"] = run.method_id
    if run.plan_id is not None:
        event_payload["plan_id"] = run.plan_id
    if run.current_step_id is not None:
        event_payload["step_id"] = run.current_step_id
    return WorkEvent(
        event_id=f"{run.run_id}-event-{sequence}",
        kind=kind,
        run_id=run.run_id,
        session_id=run.session_id,
        domain=run.domain,
        operation_id=run.operation_id,
        sequence=sequence,
        created_at=created_at,
        delivery_hint=delivery_hint,
        payload=event_payload,
    )


def _operation_payload(
    *,
    text: str,
    images: Sequence[object] | None,
    method_id: str | None,
    plan_id: str | None,
    step_id: str | None,
    step_index: int | None,
    step_title: str | None,
    planned_constraint: Mapping[str, object] | None,
    audit_policy: Mapping[str, object] | None,
    plan_facts: Mapping[str, object] | None,
    step_facts: Mapping[str, object] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {"text": text}
    if images is not None:
        payload["image_count"] = len(images)
    if method_id is not None:
        payload["method_id"] = method_id
    if plan_id is not None:
        payload["plan_id"] = plan_id
    if step_id is not None:
        payload["step_id"] = step_id
    if step_index is not None:
        payload["step_index"] = step_index
    if step_title is not None:
        payload["step_title"] = step_title
    if planned_constraint:
        payload["planned_constraint"] = dict(planned_constraint)
    if audit_policy:
        payload["audit_policy"] = dict(audit_policy)
    if plan_facts:
        payload["plan_facts"] = dict(plan_facts)
    if step_facts:
        payload["step_facts"] = dict(step_facts)
    return payload


def _step_payload(
    *,
    step_index: int | None,
    step_title: str | None,
    planned_constraint: Mapping[str, object] | None = None,
    audit_policy: Mapping[str, object] | None = None,
    plan_facts: Mapping[str, object] | None = None,
    step_facts: Mapping[str, object] | None = None,
    error: BaseException | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"source_type": "work_shell"}
    if step_index is not None:
        payload["step_index"] = step_index
    if step_title is not None:
        payload["step_title"] = step_title
    if planned_constraint:
        payload["planned_constraint"] = dict(planned_constraint)
    if audit_policy:
        payload["audit_policy"] = dict(audit_policy)
    if plan_facts:
        payload["plan_facts"] = dict(plan_facts)
    if step_facts:
        payload["step_facts"] = dict(step_facts)
    if error is not None:
        payload["error"] = str(error)
    return payload


def _event_log_entry_from_work_event(event: WorkEvent) -> EventLogEntry:
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


__all__ = ["CodingWorkShell", "PromptSession"]
