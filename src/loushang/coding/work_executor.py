from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from loushang.coding.event import project_runtime_event_to_session_event
from loushang.coding.work_projection import (
    CodingWorkFactProjectionContext,
    project_agent_event_to_work_facts,
)
from loushang.harness.agent_transcript import create_agent_transcript_message_codec
from loushang.harness.events import RuntimeEvent
from loushang.work.ports import WorkExecutionContext
from loushang.work.types import WorkOperation, WorkRunSpec

RuntimeEventListener = Callable[[RuntimeEvent[object]], Awaitable[None] | None]
_MESSAGE_CODEC = create_agent_transcript_message_codec()
serialize_agent_message = _MESSAGE_CODEC.serialize


class PromptSession(Protocol):
    def subscribe_runtime_events(
        self,
        listener: RuntimeEventListener,
    ) -> Callable[[], None]: ...

    def prompt(
        self, text: str, *, images: Sequence[object] | None = None
    ) -> Awaitable[None]: ...


@dataclass(frozen=True)
class SubmitCodingTurn:
    text: str
    images: Sequence[object] | None = None
    method_id: str | None = None
    plan_id: str | None = None
    step_id: str | None = None
    step_index: int | None = None
    step_title: str | None = None
    planned_constraint: Mapping[str, object] | None = None
    audit_policy: Mapping[str, object] | None = None
    plan_facts: Mapping[str, object] | None = None
    step_facts: Mapping[str, object] | None = None
    emit_plan_start: bool = True
    emit_plan_completion: bool = True
    emit_plan_failure: bool = True

    def to_operation(self, *, session_id: str, operation_id: str) -> WorkOperation:
        payload: dict[str, object] = {"text": self.text}
        if self.images is not None:
            payload["image_count"] = len(self.images)
        if self.method_id is not None:
            payload["method_id"] = self.method_id
        if self.plan_id is not None:
            payload["plan_id"] = self.plan_id
        if self.step_id is not None:
            payload["step_id"] = self.step_id
        if self.step_index is not None:
            payload["step_index"] = self.step_index
        if self.step_title is not None:
            payload["step_title"] = self.step_title
        if self.planned_constraint:
            payload["planned_constraint"] = dict(self.planned_constraint)
        if self.audit_policy:
            payload["audit_policy"] = dict(self.audit_policy)
        if self.plan_facts:
            payload["plan_facts"] = dict(self.plan_facts)
        if self.step_facts:
            payload["step_facts"] = dict(self.step_facts)
        return WorkOperation(
            operation_id=operation_id,
            kind="SubmitCodingTurn",
            session_id=session_id,
            domain="coding",
            payload=payload,
        )

    def to_run_spec(self, *, run_id: str | None) -> WorkRunSpec:
        scope_payload: dict[str, object] = {"source_type": "work_shell"}
        if self.step_index is not None:
            scope_payload["step_index"] = self.step_index
        if self.step_title is not None:
            scope_payload["step_title"] = self.step_title
        if self.planned_constraint:
            scope_payload["planned_constraint"] = dict(self.planned_constraint)
        if self.audit_policy:
            scope_payload["audit_policy"] = dict(self.audit_policy)
        if self.plan_facts:
            scope_payload["plan_facts"] = dict(self.plan_facts)
        if self.step_facts:
            scope_payload["step_facts"] = dict(self.step_facts)
        return WorkRunSpec(
            run_id=run_id,
            method_id=self.method_id,
            plan_id=self.plan_id,
            step_id=self.step_id,
            run_event_payload={"source_type": "work_shell"},
            scope_event_payload=scope_payload,
            emit_plan_start=self.emit_plan_start,
            emit_plan_completion=self.emit_plan_completion,
            emit_plan_failure=self.emit_plan_failure,
        )


@dataclass(frozen=True)
class CodingDomainExecutor:
    session: PromptSession
    turn: SubmitCodingTurn

    async def execute(
        self,
        operation: WorkOperation,
        context: WorkExecutionContext,
    ) -> object:
        if operation.kind != "SubmitCodingTurn" or operation.domain != "coding":
            raise ValueError(
                f"Coding executor cannot execute {operation.domain}:{operation.kind}"
            )

        async def listener(event: RuntimeEvent[object]) -> None:
            projected = project_runtime_event_to_session_event(event)
            if projected is None:
                return
            facts = project_agent_event_to_work_facts(
                projected,
                context=CodingWorkFactProjectionContext(
                    source_event_ref=event.event_id,
                    message_serializer=serialize_agent_message,
                ),
            )
            for fact in facts:
                context.publish(fact)

        unsubscribe = self.session.subscribe_runtime_events(listener)
        try:
            if self.turn.images is None:
                await self.session.prompt(self.turn.text)
            else:
                await self.session.prompt(self.turn.text, images=self.turn.images)
        finally:
            unsubscribe()
        return None


__all__ = ["CodingDomainExecutor", "PromptSession", "SubmitCodingTurn"]
