from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from loushang.coding.event import project_runtime_event_to_session_event
from loushang.harness.agent_transcript import create_agent_transcript_message_codec
from loushang.harness.events import RuntimeEvent
from loushang.work.agent_projection import (
    AgentWorkFactProjectionContext,
    project_agent_event_to_work_facts,
)
from loushang.work.ports import WorkExecutionContext
from loushang.work.types import (
    WorkCancellationOutcome,
    WorkOperation,
    WorkRunSpec,
    WorkStepSpec,
)

RuntimeEventListener = Callable[[RuntimeEvent[object]], Awaitable[None] | None]
CodingTurnHook = Callable[
    ["SubmitCodingTurn", int, int], Awaitable[None] | None
]
_MESSAGE_CODEC = create_agent_transcript_message_codec()
serialize_agent_message = _MESSAGE_CODEC.serialize


class PromptSession(Protocol):
    def subscribe_runtime_events(
        self,
        listener: RuntimeEventListener,
    ) -> Callable[[], None]: ...

    def prompt(
        self,
        text: str,
        *,
        images: Sequence[object] | None = None,
        streaming_behavior: str | None = None,
        source: str | None = None,
    ) -> Awaitable[None]: ...

    def abort(self) -> object: ...

    def wait_for_idle(self) -> Awaitable[None]: ...


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
    streaming_behavior: str | None = None
    source: str | None = None
    follow_up_messages: tuple[str, ...] = ()

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
        if self.streaming_behavior is not None:
            payload["streaming_behavior"] = self.streaming_behavior
        if self.follow_up_messages:
            payload["follow_up_count"] = len(self.follow_up_messages)
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
        )

    def to_step_spec(self) -> WorkStepSpec:
        if self.step_id is None:
            raise ValueError("a planned Coding turn requires step_id")
        return WorkStepSpec(
            step_id=self.step_id,
            payload=self.to_run_spec(run_id=None).scope_event_payload,
        )


@dataclass(frozen=True)
class CodingDomainExecutor:
    session: PromptSession
    turn: SubmitCodingTurn | None = None
    turns: tuple[SubmitCodingTurn, ...] = ()
    before_turn: CodingTurnHook | None = None
    after_turn: CodingTurnHook | None = None
    wait_for_idle_after_prompt: bool = False

    async def execute(
        self,
        operation: WorkOperation,
        context: WorkExecutionContext,
    ) -> WorkCancellationOutcome:
        if operation.kind != "SubmitCodingTurn" or operation.domain != "coding":
            raise ValueError(
                f"Coding executor cannot execute {operation.domain}:{operation.kind}"
            )

        turn = self._resolve_turn(operation, context)

        async def listener(event: RuntimeEvent[object]) -> None:
            projected = project_runtime_event_to_session_event(event)
            if projected is None:
                return
            facts = project_agent_event_to_work_facts(
                projected,
                context=AgentWorkFactProjectionContext(
                    source_event_ref=event.event_id,
                    message_serializer=serialize_agent_message,
                ),
            )
            for fact in facts:
                context.publish(fact)

        unsubscribe = self.session.subscribe_runtime_events(listener)
        try:
            messages = (turn.text, *turn.follow_up_messages)
            for message_index, text in enumerate(messages):
                active_turn = turn if message_index == 0 else SubmitCodingTurn(text=text)
                await self._call_hook(
                    self.before_turn, active_turn, message_index, len(messages)
                )
                await self._prompt(active_turn)
                if self.wait_for_idle_after_prompt:
                    await self.session.wait_for_idle()
                await self._call_hook(
                    self.after_turn, active_turn, message_index, len(messages)
                )
        finally:
            unsubscribe()
        return None

    async def cancel_and_wait(
        self,
        operation: WorkOperation,
        context: WorkExecutionContext,
    ) -> object:
        del operation, context
        abort = getattr(self.session, "abort", None)
        if not callable(abort):
            return WorkCancellationOutcome.unsupported()
        result = abort()
        if inspect.isawaitable(result):
            await result
        wait_for_idle = getattr(self.session, "wait_for_idle", None)
        if callable(wait_for_idle):
            await wait_for_idle()
        return WorkCancellationOutcome.settled()

    def _resolve_turn(
        self, operation: WorkOperation, context: WorkExecutionContext
    ) -> SubmitCodingTurn:
        if self.turns:
            index = context.step_index
            if index is None or index < 0 or index >= len(self.turns):
                raise ValueError("Coding plan execution has no turn for the active step")
            return self.turns[index]
        if self.turn is not None:
            return self.turn
        text = operation.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("SubmitCodingTurn payload requires non-empty text")
        streaming_behavior = operation.payload.get("streaming_behavior")
        if streaming_behavior is not None and (
            not isinstance(streaming_behavior, str) or not streaming_behavior
        ):
            raise ValueError("streaming_behavior must be a non-empty string when set")
        return SubmitCodingTurn(
            text=text,
            streaming_behavior=streaming_behavior,
            source="channel",
        )

    async def _prompt(self, turn: SubmitCodingTurn) -> None:
        if turn.streaming_behavior is not None or turn.source is not None:
            if turn.images is None:
                await self.session.prompt(
                    turn.text,
                    streaming_behavior=turn.streaming_behavior,
                    source=turn.source,
                )
            else:
                await self.session.prompt(
                    turn.text,
                    images=turn.images,
                    streaming_behavior=turn.streaming_behavior,
                    source=turn.source,
                )
        elif turn.images is not None:
            await self.session.prompt(turn.text, images=turn.images)
        else:
            await self.session.prompt(turn.text)

    @staticmethod
    async def _call_hook(
        hook: CodingTurnHook | None,
        turn: SubmitCodingTurn,
        turn_index: int,
        turn_count: int,
    ) -> None:
        if hook is None:
            return
        result = hook(turn, turn_index, turn_count)
        if inspect.isawaitable(result):
            await result


__all__ = [
    "CodingDomainExecutor",
    "CodingTurnHook",
    "PromptSession",
    "SubmitCodingTurn",
]
