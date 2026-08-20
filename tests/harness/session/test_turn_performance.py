from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

from loushang.agent.types import AgentEvent, ModelCallPreparation
from loushang.ai import Context, Model
from loushang.ai.options import CallOptions
from loushang.ai.prepared_request import PreparedModelRequest
from loushang.ai.types import AssistantMessage, TextPart, Usage
from loushang.foundation.json import JSONValue
from loushang.foundation.observability.runtime import observability_runtime_context
from loushang.harness.session import PromptController
from loushang.harness.session.turn_performance import TurnStartPerformanceRuntime


class _Clock:
    def __init__(self) -> None:
        self.now_ns = 0

    def __call__(self) -> int:
        return self.now_ns

    def advance_ms(self, value: int) -> None:
        self.now_ns += value * 1_000_000


class _Log:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, str, dict[str, JSONValue]]] = []

    def debug_event(self, scope: str, name: str, **data: JSONValue) -> None:
        if self.fail:
            raise RuntimeError("logging unavailable")
        self.events.append((scope, name, data))


def _request() -> PreparedModelRequest:
    return PreparedModelRequest(
        invocation_id="invocation-1",
        attempt=1,
        provider_id="provider-1",
        endpoint_id="endpoint-1",
        api="test-api",
        model_id="model-1",
        mode="stream",
        payload={"messages": []},
    )


def _preparation() -> ModelCallPreparation:
    return ModelCallPreparation(
        purpose="main",
        sequence=1,
        model=Model(
            id="model-1",
            provider="provider-1",
            endpoint="endpoint-1",
            api="test-api",
        ),
        context=Context(),
        options=CallOptions(),
    )


def _assistant_message() -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text="private response")],
        api="test-api",
        provider="provider-1",
        endpoint="endpoint-1",
        model="model-1",
        response_id="response-1",
        usage=Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total_tokens=0,
            cost=None,
        ),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )


def test_turn_start_performance_records_content_free_cross_layer_timing() -> None:
    clock = _Clock()
    log = _Log()
    runtime = TurnStartPerformanceRuntime(
        session_id="session-1",
        clock=clock,
        turn_id_factory=lambda: "turn-1",
        log=log,
    )

    timing = runtime.begin(source="tui")
    clock.advance_ms(2)
    timing.mark("preflight_completed")
    clock.advance_ms(3)
    timing.activate()
    clock.advance_ms(2)
    runtime.observe_agent_event(cast(AgentEvent, {"type": "turn_start"}))
    clock.advance_ms(4)
    runtime.model_call_prepare_started(_preparation())
    clock.advance_ms(2)
    runtime.model_call_prepared()
    clock.advance_ms(4)
    runtime.model_input_commit_started(_request())
    clock.advance_ms(6)
    runtime.transport_ready(_request())
    message = _assistant_message()
    clock.advance_ms(8)
    runtime.observe_agent_event(
        cast(AgentEvent, {"type": "message_start", "message": message})
    )
    clock.advance_ms(2)
    runtime.observe_agent_event(
        cast(
            AgentEvent,
            {
                "type": "message_update",
                "message": message,
                "assistant_message_event": {
                    "type": "text_start",
                    "content_index": 0,
                    "partial": message,
                },
            },
        )
    )
    clock.advance_ms(4)
    runtime.observe_agent_event(
        cast(
            AgentEvent,
            {
                "type": "message_update",
                "message": message,
                "assistant_message_event": {
                    "type": "text_delta",
                    "content_index": 0,
                    "delta": "private response",
                    "partial": message,
                },
            },
        )
    )
    clock.advance_ms(6)
    timing.finish("completed")

    assert len(log.events) == 1
    scope, name, data = log.events[0]
    assert (scope, name) == ("turn.start.performance", "turn")
    assert data["session_id"] == "session-1"
    assert data["turn_id"] == "turn-1"
    assert data["source"] == "tui"
    assert data["outcome"] == "completed"
    assert data["invocation_id"] == "invocation-1"
    assert data["provider_id"] == "provider-1"
    assert data["endpoint_id"] == "endpoint-1"
    assert data["api_id"] == "test-api"
    assert data["model_id"] == "model-1"
    assert data["local_ready_ms"] == 23.0
    assert data["startup_ms"] == 37.0
    assert data["total_ms"] == 43.0
    assert data["phases"] == {
        "input_pipeline": {"total_ms": 5.0},
        "agent_to_model_call": {"total_ms": 6.0},
        "model_call_prepare": {"total_ms": 2.0},
        "model_input_commit": {"total_ms": 6.0},
        "provider_first_response": {"total_ms": 8.0},
        "provider_first_content": {"total_ms": 14.0},
    }
    serialized = repr(data)
    assert "private response" not in serialized
    assert "messages" not in serialized


def test_turn_start_performance_keeps_queued_submission_separate() -> None:
    clock = _Clock()
    log = _Log()
    runtime = TurnStartPerformanceRuntime(
        session_id="session-1",
        clock=clock,
        turn_id_factory=iter(("active-turn", "queued-turn")).__next__,
        log=log,
    )

    active = runtime.begin(source=None)
    active.activate()
    queued = runtime.begin(source="rpc")
    clock.advance_ms(3)
    queued.mark_queued()
    queued.finish("completed")
    clock.advance_ms(2)
    runtime.observe_agent_event(cast(AgentEvent, {"type": "turn_start"}))
    active.finish("completed")

    queued_event = log.events[0][2]
    active_event = log.events[1][2]
    assert queued_event["turn_id"] == "queued-turn"
    assert queued_event["source"] == "rpc"
    assert queued_event["outcome"] == "queued"
    assert queued_event["queued"] is True
    assert active_event["turn_id"] == "active-turn"
    assert active_event["outcome"] == "completed"
    assert "agent_loop_started" in cast(dict[str, JSONValue], active_event["milestones"])


def test_turn_start_performance_logging_is_best_effort() -> None:
    runtime = TurnStartPerformanceRuntime(session_id="session-1", log=_Log(fail=True))

    runtime.begin(source=None).finish("completed")


def test_turn_start_performance_reaches_the_real_trace_sink(tmp_path: Path) -> None:
    trace_path = tmp_path / "turn-trace.jsonl"

    with observability_runtime_context(
        session_id="session-1",
        cwd=tmp_path,
        mode="tui",
        trace_path=trace_path,
        trace_scopes=frozenset({"turn.start.performance"}),
    ):
        runtime = TurnStartPerformanceRuntime(
            session_id="session-1",
            turn_id_factory=lambda: "turn-1",
        )
        runtime.begin(source="tui").finish("completed")

    records = [
        json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["kind"] == "debug_event"
    assert records[0]["scope"] == "turn.start.performance"
    assert records[0]["name"] == "turn"
    assert records[0]["data"]["turn_id"] == "turn-1"


class _PromptAgent:
    is_streaming = False

    def __init__(self) -> None:
        self.state = type("State", (), {"system_prompt": "base"})()
        self.prompted = False

    async def prompt(self, messages: list[object]) -> None:
        del messages
        self.prompted = True


class _PromptQueue:
    def drain_next_turn_messages(self) -> list[object]:
        return []


def test_prompt_controller_reports_submission_pipeline_without_prompt_content() -> None:
    clock = _Clock()
    log = _Log()
    tracker = TurnStartPerformanceRuntime(
        session_id="session-1",
        clock=clock,
        turn_id_factory=lambda: "turn-1",
        log=log,
    )
    agent = _PromptAgent()

    async def scenario() -> None:
        controller = PromptController(
            agent=agent,
            queue_controller=_PromptQueue(),
            get_extension_runner=lambda: None,
            get_cwd=lambda: "/tmp/project",
            extract_extension_command_invocation=lambda text: None,
            execute_command_async=lambda name, args: _unused_async(name, args),
            preflight_user_input_async=lambda text, **kwargs: _prompt_preflight(
                text,
                clock=clock,
                **kwargs,
            ),
            before_agent_start_system_prompt_options=lambda: {},
            sync_extension_diagnostics=lambda **kwargs: None,
            compact_before_prompt_async=lambda: _advance_async(clock, 3),
            turn_performance=tracker,
        )

        await controller.prompt("private prompt", source="tui")

    asyncio.run(scenario())

    assert agent.prompted
    data = log.events[0][2]
    assert data["source"] == "tui"
    milestones = cast(dict[str, JSONValue], data["milestones"])
    assert set(milestones) >= {
        "submission_received",
        "preflight_completed",
        "before_run_completed",
        "before_start_completed",
        "agent_run_dispatched",
        "finished",
    }
    assert data["startup_ms"] is None
    assert "private prompt" not in repr(data)


async def _prompt_preflight(
    text: str,
    *,
    clock: _Clock,
    allow_extension_commands: bool = True,
) -> object:
    del allow_extension_commands
    clock.advance_ms(2)
    return type("Preflight", (), {"text": text, "consumed": False})()


async def _advance_async(clock: _Clock, milliseconds: int) -> None:
    clock.advance_ms(milliseconds)


async def _unused_async(name: str, args: str) -> None:
    del name, args
