from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime


class FakePromptSession:
    def __init__(self, events: list[dict[str, object]], *, error: Exception | None = None) -> None:
        self.events = events
        self.error = error
        self.prompts: list[str] = []
        self.listeners: list[Callable[[dict[str, object]], Awaitable[None] | None]] = []

    def subscribe(self, listener: Callable[[dict[str, object]], Awaitable[None] | None]) -> Callable[[], None]:
        self.listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self.listeners:
                self.listeners.remove(listener)

        return unsubscribe

    async def prompt(self, text: str) -> None:
        self.prompts.append(text)
        if self.error is not None:
            raise self.error
        for event in self.events:
            for listener in list(self.listeners):
                result = listener(event)
                if result is not None:
                    await result


def test_coding_work_shell_wraps_prompt_and_logs_operation_run_and_projected_events() -> None:
    from loushang.work import CodingWorkShell, InMemoryEventLogBackend

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = FakePromptSession(
            events=[
                {
                    "type": "message_update",
                    "message": {"role": "assistant"},
                    "assistant_message_event": {"type": "text_delta", "text": "done"},
                },
                {
                    "type": "tool_execution_end",
                    "tool_call_id": "tool-1",
                    "tool_name": "pytest",
                    "result": {"output": "passed"},
                    "is_error": False,
                },
            ],
        )
        shell = CodingWorkShell(
            session=session,
            event_log=event_log,
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )

        run = await shell.submit_coding_turn(
            "fix this bug",
            session_id="session-1",
            operation_id="op-1",
            run_id="run-1",
        )

        assert session.prompts == ["fix this bug"]
        assert run.status == "completed"
        assert len(session.listeners) == 0

        entries = event_log.query(run_id="run-1")
        assert [entry.entry_type for entry in entries] == ["operation", "event", "event", "event", "event"]
        assert entries[0].payload == {
            "kind": "SubmitCodingTurn",
            "domain": "coding",
            "payload": {"text": "fix this bug"},
        }
        assert [entry.payload["kind"] for entry in entries[1:]] == [
            "WorkRunStarted",
            "ContentDelta",
            "ToolCallCompleted",
            "WorkRunCompleted",
        ]
        assert entries[2].payload["delivery_hint"] == "coalesce"
        assert entries[3].payload["delivery_hint"] == "coalesce"
        assert entries[4].payload["delivery_hint"] == "immediate"

    asyncio.run(scenario())


def test_coding_work_shell_logs_tool_policy_and_approval_audit_events() -> None:
    from loushang.work import CodingWorkShell, InMemoryEventLogBackend

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = FakePromptSession(
            events=[
                {
                    "type": "tool_policy_evaluated",
                    "tool_call_id": "tool-1",
                    "tool_name": "write",
                    "policy_disposition": "ask",
                    "policy_code": "tool_requires_approval",
                    "policy_reason": "Tool write requires approval",
                    "approval_required": True,
                    "argument_keys": ["content", "path"],
                    "path": "/repo/approved.txt",
                },
                {
                    "type": "tool_approval_requested",
                    "tool_call_id": "tool-1",
                    "tool_name": "write",
                    "action_id": "approval-1",
                    "policy_code": "tool_requires_approval",
                    "policy_reason": "Tool write requires approval",
                    "argument_keys": ["content", "path"],
                    "path": "/repo/approved.txt",
                },
                {
                    "type": "tool_approval_resolved",
                    "tool_call_id": "tool-1",
                    "tool_name": "write",
                    "action_id": "approval-1",
                    "approval_decision": "allow",
                    "policy_code": "tool_requires_approval",
                    "policy_reason": "Tool write requires approval",
                },
            ],
        )
        shell = CodingWorkShell(
            session=session,
            event_log=event_log,
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )

        await shell.submit_coding_turn(
            "write approved file",
            session_id="session-1",
            operation_id="op-1",
            run_id="run-1",
        )

        entries = event_log.query(run_id="run-1")
        assert [entry.payload["kind"] for entry in entries] == [
            "SubmitCodingTurn",
            "WorkRunStarted",
            "ToolPolicyEvaluated",
            "ToolApprovalRequested",
            "ToolApprovalResolved",
            "WorkRunCompleted",
        ]
        assert entries[2].payload["payload"]["tool_call_id"] == "tool-1"
        assert entries[2].payload["payload"]["policy_disposition"] == "ask"
        assert entries[3].payload["payload"]["action_id"] == "approval-1"
        assert entries[4].payload["payload"]["approval_decision"] == "allow"
        assert entries[2].payload["delivery_hint"] == "immediate"
        assert entries[3].payload["delivery_hint"] == "immediate"
        assert entries[4].payload["delivery_hint"] == "immediate"

    asyncio.run(scenario())


def test_coding_work_shell_jsonl_log_can_replay_persisted_turn(tmp_path) -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage
    from loushang.work import CodingWorkShell, JsonlEventLogBackend

    usage = Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={})
    assistant = AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text="done")],
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=usage,
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )

    async def scenario() -> None:
        log_path = tmp_path / "events.jsonl"
        session = FakePromptSession(
            events=[
                {
                    "type": "message_update",
                    "message": {"role": "assistant"},
                    "assistant_message_event": {"type": "text_delta", "text": "done"},
                },
                {"type": "message_end", "message": assistant},
            ],
        )
        shell = CodingWorkShell(
            session=session,
            event_log=JsonlEventLogBackend(log_path),
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )

        run = await shell.submit_coding_turn(
            "persist this turn",
            session_id="session-1",
            operation_id="op-1",
            run_id="run-1",
        )

        replayed = JsonlEventLogBackend(log_path).query(run_id=run.run_id)

        assert [entry.payload["kind"] for entry in replayed] == [
            "SubmitCodingTurn",
            "WorkRunStarted",
            "ContentDelta",
            "ContentDelta",
            "WorkRunCompleted",
        ]
        assert replayed[3].payload["payload"]["message"]["role"] == "assistant"
        assert replayed[4].payload["delivery_hint"] == "immediate"

    asyncio.run(scenario())


def test_coding_work_shell_records_method_id_as_metadata_only() -> None:
    from loushang.work import CodingWorkShell, InMemoryEventLogBackend

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = FakePromptSession(events=[])
        shell = CodingWorkShell(
            session=session,
            event_log=event_log,
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )

        run = await shell.submit_coding_turn(
            "fix this bug",
            session_id="session-1",
            operation_id="op-1",
            run_id="run-1",
            method_id="method:task:review",
        )

        assert session.prompts == ["fix this bug"]
        assert run.method_id == "method:task:review"

        entries = event_log.query(run_id="run-1")
        assert entries[0].payload["payload"]["method_id"] == "method:task:review"
        assert entries[1].payload["payload"]["method_id"] == "method:task:review"
        assert entries[2].payload["payload"]["method_id"] == "method:task:review"

    asyncio.run(scenario())


def test_coding_work_shell_records_plan_and_step_lifecycle_events() -> None:
    from loushang.work import CodingWorkShell, InMemoryEventLogBackend

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = FakePromptSession(events=[])
        shell = CodingWorkShell(
            session=session,
            event_log=event_log,
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )
        plan_facts = {
            "plan_id": "plan:method:task:review",
            "method_id": "method:task:review",
            "mode": "fixed",
        }
        step_facts = {
            "step_id": "inspect",
            "title": "Inspect current changes",
            "step_index": 0,
            "step_count": 2,
        }

        run = await shell.submit_coding_turn(
            "inspect current changes",
            session_id="session-1",
            operation_id="op-1",
            run_id="run-1",
            method_id="method:task:review",
            plan_id="plan:method:task:review",
            step_id="inspect",
            step_index=0,
            step_title="Inspect current changes",
            planned_constraint={"level": "reasoned", "requires_reason": True},
            audit_policy={"record": ["status", "reason"]},
            plan_facts=plan_facts,
            step_facts=step_facts,
        )

        assert run.status == "completed"
        assert run.method_id == "method:task:review"
        assert run.plan_id == "plan:method:task:review"
        assert run.current_step_id == "inspect"

        entries = event_log.query(run_id="run-1")
        assert [entry.payload["kind"] for entry in entries] == [
            "SubmitCodingTurn",
            "WorkRunStarted",
            "WorkPlanStarted",
            "WorkStepStarted",
            "WorkStepCompleted",
            "WorkPlanCompleted",
            "WorkRunCompleted",
        ]
        assert entries[0].payload["payload"] == {
            "text": "inspect current changes",
            "method_id": "method:task:review",
            "plan_id": "plan:method:task:review",
            "step_id": "inspect",
            "step_index": 0,
            "step_title": "Inspect current changes",
            "planned_constraint": {"level": "reasoned", "requires_reason": True},
            "audit_policy": {"record": ["status", "reason"]},
            "plan_facts": plan_facts,
            "step_facts": step_facts,
        }
        assert entries[2].payload["delivery_hint"] == "coalesce"
        assert entries[3].payload["delivery_hint"] == "coalesce"
        assert entries[4].payload["delivery_hint"] == "coalesce"
        assert entries[5].payload["delivery_hint"] == "final_only"
        assert entries[3].payload["payload"] == {
            "source_type": "work_shell",
            "method_id": "method:task:review",
            "plan_id": "plan:method:task:review",
            "step_id": "inspect",
            "step_index": 0,
            "step_title": "Inspect current changes",
            "planned_constraint": {"level": "reasoned", "requires_reason": True},
            "audit_policy": {"record": ["status", "reason"]},
            "plan_facts": plan_facts,
            "step_facts": step_facts,
        }
        assert entries[2].payload["payload"]["plan_facts"] == plan_facts
        assert entries[2].payload["payload"]["step_facts"] == step_facts
        assert entries[4].payload["payload"]["plan_facts"] == plan_facts
        assert entries[4].payload["payload"]["step_facts"] == step_facts
        assert entries[5].payload["payload"]["plan_facts"] == plan_facts
        assert entries[5].payload["payload"]["step_facts"] == step_facts

    asyncio.run(scenario())


def test_coding_work_shell_can_suppress_plan_boundaries_for_middle_step() -> None:
    from loushang.work import CodingWorkShell, InMemoryEventLogBackend

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = FakePromptSession(events=[])
        shell = CodingWorkShell(
            session=session,
            event_log=event_log,
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )

        run = await shell.submit_coding_turn(
            "verify current changes",
            session_id="session-1",
            operation_id="op-1",
            run_id="run-1",
            method_id="method:task:review",
            plan_id="plan:method:task:review",
            step_id="verify",
            step_index=1,
            step_title="Run focused checks",
            emit_plan_start=False,
            emit_plan_completion=False,
        )

        assert run.status == "completed"
        entries = event_log.query(run_id="run-1")
        assert [entry.payload["kind"] for entry in entries] == [
            "SubmitCodingTurn",
            "WorkRunStarted",
            "WorkStepStarted",
            "WorkStepCompleted",
            "WorkRunCompleted",
        ]

    asyncio.run(scenario())


def test_coding_work_shell_records_plan_failure_even_when_plan_boundaries_are_suppressed() -> None:
    from loushang.work import CodingWorkShell, InMemoryEventLogBackend

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = FakePromptSession(events=[], error=RuntimeError("middle step failed"))
        shell = CodingWorkShell(
            session=session,
            event_log=event_log,
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )

        try:
            await shell.submit_coding_turn(
                "verify current changes",
                session_id="session-1",
                operation_id="op-1",
                run_id="run-1",
                method_id="method:task:review",
                plan_id="plan:method:task:review",
                step_id="verify",
                step_index=1,
                step_title="Run focused checks",
                emit_plan_start=False,
                emit_plan_completion=False,
            )
        except RuntimeError as error:
            assert str(error) == "middle step failed"
        else:
            raise AssertionError("expected prompt failure")

        entries = event_log.query(run_id="run-1")
        assert [entry.payload["kind"] for entry in entries] == [
            "SubmitCodingTurn",
            "WorkRunStarted",
            "WorkStepStarted",
            "WorkStepFailed",
            "WorkPlanFailed",
            "WorkRunFailed",
        ]

    asyncio.run(scenario())


def test_coding_work_shell_records_step_and_plan_failures_before_run_failure() -> None:
    from loushang.work import CodingWorkShell, InMemoryEventLogBackend

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = FakePromptSession(events=[], error=RuntimeError("agent failed"))
        shell = CodingWorkShell(
            session=session,
            event_log=event_log,
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )
        plan_facts = {"plan_id": "plan:method:task:review", "method_id": "method:task:review"}
        step_facts = {"step_id": "inspect", "step_index": 0}

        try:
            await shell.submit_coding_turn(
                "inspect current changes",
                session_id="session-1",
                operation_id="op-1",
                run_id="run-1",
                method_id="method:task:review",
                plan_id="plan:method:task:review",
                step_id="inspect",
                step_index=0,
                step_title="Inspect current changes",
                plan_facts=plan_facts,
                step_facts=step_facts,
            )
        except RuntimeError as error:
            assert str(error) == "agent failed"
        else:
            raise AssertionError("expected prompt failure")

        entries = event_log.query(run_id="run-1")
        assert [entry.payload["kind"] for entry in entries] == [
            "SubmitCodingTurn",
            "WorkRunStarted",
            "WorkPlanStarted",
            "WorkStepStarted",
            "WorkStepFailed",
            "WorkPlanFailed",
            "WorkRunFailed",
        ]
        assert entries[4].payload["delivery_hint"] == "immediate"
        assert entries[5].payload["delivery_hint"] == "immediate"
        assert entries[4].payload["payload"]["error"] == "agent failed"
        assert entries[5].payload["payload"]["error"] == "agent failed"
        assert entries[4].payload["payload"]["plan_facts"] == plan_facts
        assert entries[4].payload["payload"]["step_facts"] == step_facts
        assert entries[5].payload["payload"]["plan_facts"] == plan_facts
        assert entries[5].payload["payload"]["step_facts"] == step_facts
        assert entries[6].payload["payload"]["method_id"] == "method:task:review"
        assert entries[6].payload["payload"]["plan_id"] == "plan:method:task:review"
        assert entries[6].payload["payload"]["step_id"] == "inspect"

    asyncio.run(scenario())
