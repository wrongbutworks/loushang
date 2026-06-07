from __future__ import annotations

import asyncio
from types import SimpleNamespace


class FakeWorkflowAdapter:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def run_prompt(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            return ""
        return self.responses.pop(0)


def test_run_workflow_executes_steps_and_asserts_outputs(tmp_path) -> None:
    from loushang.coding.workflow import (
        CommandExpectation,
        PromptStep,
        StepExpectation,
        Workflow,
        run_workflow,
    )

    target = tmp_path / "tmp" / "bmi.py"
    target.parent.mkdir()
    target.write_text("print('BMI ready')\n", encoding="utf-8")
    workflow = Workflow(
        name="bmi",
        steps=(
            PromptStep(
                prompt="create bmi",
                expect=StepExpectation(
                    assistant_contains=("created",),
                    files_exist=("tmp/bmi.py",),
                    files_contain={"tmp/bmi.py": "BMI"},
                    command=CommandExpectation(
                        run="python tmp/bmi.py",
                        exit_code=0,
                        stdout_contains=("BMI ready",),
                    ),
                ),
            ),
        ),
    )
    adapter = FakeWorkflowAdapter(["created tmp/bmi.py"])

    result = asyncio.run(run_workflow(workflow, adapter=adapter, cwd=tmp_path))

    assert result.ok is True
    assert adapter.prompts == ["create bmi"]
    assert result.step_results[0].assistant_text == "created tmp/bmi.py"
    assert all(check.ok for check in result.step_results[0].checks)


def test_run_workflow_reports_failed_expectation_without_stopping_later_steps(tmp_path) -> None:
    from loushang.coding.workflow import (
        PromptStep,
        StepExpectation,
        Workflow,
        run_workflow,
    )

    workflow = Workflow(
        name="chat",
        steps=(
            PromptStep(
                prompt="first",
                expect=StepExpectation(assistant_contains=("needle",)),
            ),
            PromptStep(
                prompt="second",
                expect=StepExpectation(assistant_contains=("done",)),
            ),
        ),
    )
    adapter = FakeWorkflowAdapter(["no match", "done"])

    result = asyncio.run(run_workflow(workflow, adapter=adapter, cwd=tmp_path))

    assert result.ok is False
    assert adapter.prompts == ["first", "second"]
    assert result.step_results[0].ok is False
    assert result.step_results[1].ok is True
    assert "assistant contains" in result.step_results[0].checks[0].label


def test_run_workflow_times_out_prompt_and_aborts_adapter(tmp_path) -> None:
    from loushang.coding.workflow import (
        PromptStep,
        StepExpectation,
        Workflow,
        run_workflow,
    )

    class SlowAdapter:
        def __init__(self) -> None:
            self.abort_calls = 0

        async def run_prompt(self, prompt: str) -> str:
            del prompt
            await asyncio.sleep(10)
            return "late"

        async def abort(self) -> None:
            self.abort_calls += 1

    adapter = SlowAdapter()
    workflow = Workflow(
        name="timeout",
        steps=(
            PromptStep(prompt="slow", timeout_s=0.01),
            PromptStep(prompt="after", expect=StepExpectation(assistant_contains=("after",))),
        ),
    )

    result = asyncio.run(run_workflow(workflow, adapter=adapter, cwd=tmp_path))

    assert result.ok is False
    assert len(result.step_results) == 1
    assert result.step_results[0].error == "timed out after 0.01s"
    assert adapter.abort_calls == 1


def test_run_workflow_emits_step_start_progress(tmp_path) -> None:
    from loushang.coding.workflow import PromptStep, Workflow, run_workflow

    adapter = FakeWorkflowAdapter(["ok"])
    workflow = Workflow(name="progress", steps=(PromptStep(prompt="hello"),))
    events: list[tuple[int, int, str]] = []

    result = asyncio.run(
        run_workflow(
            workflow,
            adapter=adapter,
            cwd=tmp_path,
            on_step_start=lambda index, total, step: events.append((index, total, step.prompt)),
        )
    )

    assert result.ok is True
    assert events == [(1, 1, "hello")]


def test_agent_session_adapter_supports_hold_actions_and_abort(tmp_path) -> None:
    from loushang.coding.workflow import (
        AbortStep,
        AgentSessionWorkflowAdapter,
        ExpectStep,
        FollowUpStep,
        PromptStep,
        SteerStep,
        WaitForStep,
        Workflow,
        WorkflowExpectation,
        run_workflow,
    )

    class ActionSession:
        def __init__(self) -> None:
            self.messages: list[object] = []
            self.steering: list[str] = []
            self.follow_up: list[str] = []
            self.cleared = False
            self._listeners = []
            self._release = asyncio.Event()

        def subscribe(self, listener):
            self._listeners.append(listener)
            return lambda: self._listeners.remove(listener)

        async def prompt(self, text: str, *, streaming_behavior: str | None = None) -> None:
            if streaming_behavior == "steer":
                self.steering.append(text)
                return
            if streaming_behavior == "followUp":
                self.follow_up.append(text)
                return
            user = SimpleNamespace(role="user", content=text)
            self.messages.append(user)
            await self._emit({"type": "message_start", "message": user})
            await self._emit({"type": "message_end", "message": user})
            await self._release.wait()

        def abort(self) -> None:
            self._release.set()

        def clear_queue(self):
            self.cleared = True
            self.steering.clear()
            self.follow_up.clear()
            return {"steering": [], "follow_up": []}

        def get_steering_messages(self):
            return list(self.steering)

        def get_follow_up_messages(self):
            return list(self.follow_up)

        async def _emit(self, event: dict) -> None:
            for listener in list(self._listeners):
                result = listener(event)
                if asyncio.iscoroutine(result):
                    await result

    session = ActionSession()
    adapter = AgentSessionWorkflowAdapter(session)
    workflow = Workflow(
        name="real adapter actions",
        steps=(
            PromptStep(prompt="long", hold=True),
            WaitForStep(event="run.started"),
            SteerStep(text="change direction"),
            FollowUpStep(text="later"),
            AbortStep(),
            WaitForStep(event="run.aborted"),
            ExpectStep(expect=WorkflowExpectation(queue={"steering": (), "follow_up": ()})),
        ),
    )

    result = asyncio.run(run_workflow(workflow, adapter=adapter, cwd=tmp_path))

    assert result.ok is True
    assert session.cleared is True
    assert [event.type for event in adapter.events()] == [
        "run.started",
        "queue.steer_added",
        "queue.follow_up_added",
        "run.aborted",
    ]


def test_agent_session_adapter_exposes_public_fact_snapshots(tmp_path) -> None:
    from loushang.coding.workflow import (
        AgentSessionWorkflowAdapter,
        ExpectStep,
        Workflow,
        WorkflowExpectation,
        run_workflow,
    )

    class FactSession:
        def subscribe(self, listener):
            del listener
            return lambda: None

        def get_session_state(self) -> dict[str, object]:
            return {
                "runStatus": "idle",
                "pendingMessageCount": 0,
            }

        def get_session_stats(self) -> dict[str, object]:
            return {
                "totalMessages": 2,
                "tokens": {"total": 34},
                "latestCompaction": {"entryId": "compact-1"},
            }

        def get_context_usage(self) -> dict[str, object]:
            return {
                "messageCount": 2,
                "estimatedContextTokens": 34,
                "compactPercent": 80,
            }

    adapter = AgentSessionWorkflowAdapter(FactSession())
    workflow = Workflow(
        name="facts",
        steps=(
            ExpectStep(
                expect=WorkflowExpectation(
                    session_state={"runStatus": "idle", "pendingMessageCount": 0},
                    session_stats={
                        "totalMessages": 2,
                        "tokens": {"total": 34},
                        "latestCompaction": {"entryId": "compact-1"},
                    },
                    context_usage={
                        "messageCount": 2,
                        "estimatedContextTokens": 34,
                        "compactPercent": 80,
                    },
                )
            ),
        ),
    )

    result = asyncio.run(run_workflow(workflow, adapter=adapter, cwd=tmp_path))

    assert result.ok is True
    assert [check.label for check in result.step_results[0].checks] == [
        "session_state.runStatus",
        "session_state.pendingMessageCount",
        "session_stats.totalMessages",
        "session_stats.tokens.total",
        "session_stats.latestCompaction.entryId",
        "context_usage.messageCount",
        "context_usage.estimatedContextTokens",
        "context_usage.compactPercent",
    ]


def test_agent_session_adapter_does_not_duplicate_assistant_message_events(tmp_path) -> None:
    from loushang.coding.workflow import (
        AgentSessionWorkflowAdapter,
        PromptStep,
        Workflow,
        run_workflow,
    )

    class EventfulSession:
        def __init__(self) -> None:
            self.messages: list[object] = []
            self._listeners = []

        def subscribe(self, listener):
            self._listeners.append(listener)
            return lambda: self._listeners.remove(listener)

        async def prompt(self, text: str) -> None:
            user = SimpleNamespace(role="user", content=text)
            assistant = SimpleNamespace(role="assistant", content="done")
            self.messages.extend([user, assistant])
            await self._emit({"type": "message_end", "message": assistant})

        async def _emit(self, event: dict) -> None:
            for listener in list(self._listeners):
                result = listener(event)
                if asyncio.iscoroutine(result):
                    await result

    session = EventfulSession()
    adapter = AgentSessionWorkflowAdapter(session)
    workflow = Workflow(name="events", steps=(PromptStep(prompt="hello"),))

    result = asyncio.run(run_workflow(workflow, adapter=adapter, cwd=tmp_path))

    assert result.ok is True
    assert [event.type for event in result.events] == [
        "run.started",
        "assistant.message",
        "run.ended",
    ]
