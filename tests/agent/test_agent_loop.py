import asyncio
import inspect
from dataclasses import dataclass, replace
from typing import Any

import pytest

from loushang.agent.types import AgentContext, AgentLoopConfig, AgentToolResult
from loushang.ai.event_stream import AssistantMessageEventStream, EventStream
from loushang.ai.model import Capabilities, Model
from loushang.ai.types import (
    AssistantMessage,
    Context,
    TextPart,
    Tool,
    ToolCall,
    Usage,
    UserMessage,
)
from loushang.observability import get_problem_store, log_context, reset_observability


def _model() -> Model:
    return Model(
        id="faux-model",
        name="Faux",
        provider="faux",
        endpoint="anthropic-messages",
        capabilities=Capabilities(
            reasoning=False,
            input=("text",),
            context_window=128000,
            max_tokens=4096,
        ),
    )


def _usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost={},
    )


def _assistant_text_message(text: str) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text=text)],
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=_usage(),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )


def _assistant_tool_call_message() -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[
            ToolCall(
                type="toolCall",
                id="tc_1",
                name="calc",
                arguments={"x": 1},
            )
        ],
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=_usage(),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )


def _assistant_tool_call_message_with_calls(tool_calls: list[ToolCall]) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=tool_calls,
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=_usage(),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )


def _stream_with_final_message(message: AssistantMessage) -> AssistantMessageEventStream:
    stream = AssistantMessageEventStream()
    stream.push({"type": "start", "partial": message})
    if message.content and isinstance(message.content[0], TextPart):
        stream.push({"type": "text_start", "content_index": 0, "partial": message})
        stream.push({"type": "text_delta", "content_index": 0, "delta": message.content[0].text, "partial": message})
        stream.push({"type": "text_end", "content_index": 0, "content": message.content[0].text, "partial": message})
    elif message.content and isinstance(message.content[0], ToolCall):
        stream.push({"type": "toolcall_start", "content_index": 0, "partial": message})
        stream.push({"type": "toolcall_delta", "content_index": 0, "delta": '{"x": 1}', "partial": message})
        stream.push({"type": "toolcall_end", "content_index": 0, "tool_call": message.content[0], "partial": message})
    stream.push({"type": "done", "reason": message.stop_reason, "message": message})  # type: ignore[typeddict-item]
    return stream


def _config(stream_fn):
    return AgentLoopConfig(
        model=_model(),
        convert_to_llm=lambda messages: [m for m in messages if isinstance(m, UserMessage) or isinstance(m, AssistantMessage) or getattr(m, "role", None) == "toolResult"],
        tool_execution="parallel",
    )


def test_agent_loop_records_problem_when_provider_request_fails() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    async def stream_fn(model, context: Context, options=None):
        del model, context, options
        raise RuntimeError("provider unavailable")

    async def emit(event):
        del event

    context = AgentContext(
        system_prompt="",
        messages=[],
        tools=[],
    )
    prompts = [UserMessage(role="user", content=[TextPart(type="text", text="hello")], timestamp=0.0)]

    reset_observability()
    try:
        with log_context(session_id="session-1", run_id=5, cwd="/repo", mode="scenario"):
            with pytest.raises(RuntimeError, match="provider unavailable"):
                asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

        records = get_problem_store().all()
        assert len(records) == 1
        assert records[0].code == "provider_request_failed"
        assert records[0].source == "provider"
        assert records[0].recoverable is True
        assert records[0].message == "provider unavailable"
        assert records[0].details == {
            "endpoint_id": "anthropic-messages",
            "model_id": "faux-model",
            "provider_id": "faux",
        }
        assert records[0].exception_type == "RuntimeError"
        assert records[0].session_id == "session-1"
        assert records[0].run_id == 5
    finally:
        reset_observability()


@dataclass
class FakeTool:
    name: str = "calc"
    description: str = "calculate"
    parameters: dict[str, Any] = None  # type: ignore[assignment]
    label: str = "Calc"
    prepare_arguments: Any = None
    execution_mode: str = "parallel"

    def __post_init__(self) -> None:
        if self.parameters is None:
            self.parameters = {
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": ["x"],
                "additionalProperties": False,
            }

    async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
        if on_update is not None:
            on_update(AgentToolResult(content=[TextPart(type="text", text="partial")], details={"progress": "half"}))
        return AgentToolResult(content=[TextPart(type="text", text=str(params["x"] + 1))], details={"value": params["x"] + 1})


def test_run_agent_loop_emits_events_for_single_assistant_turn() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    emitted: list[dict[str, Any]] = []

    async def emit(event):
        emitted.append(event)

    async def stream_fn(model, context: Context, options=None):
        assert context.system_prompt == "system"
        assert len(context.messages) == 1
        return _stream_with_final_message(_assistant_text_message("hello"))

    prompts = [UserMessage(role="user", content="hi", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[])

    new_messages = asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

    assert [event["type"] for event in emitted] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "message_start",
        "message_update",
        "message_update",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    assert len(new_messages) == 2
    assert isinstance(new_messages[-1], AssistantMessage)
    assert new_messages[-1].content[0].text == "hello"


def test_run_agent_loop_executes_tool_and_continues_with_following_turn() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    emitted: list[dict[str, Any]] = []

    async def emit(event):
        emitted.append(event)

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[FakeTool()])

    new_messages = asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

    event_types = [event["type"] for event in emitted]
    assert event_types.count("turn_start") == 2
    assert "tool_execution_start" in event_types
    assert "tool_execution_update" in event_types
    assert "tool_execution_end" in event_types
    tool_end_event = next(event for event in emitted if event["type"] == "tool_execution_end")
    assert isinstance(tool_end_event["duration_ms"], int)
    assert tool_end_event["duration_ms"] >= 0
    assert len(new_messages) == 4
    assert getattr(new_messages[2], "role", None) == "toolResult"
    assert isinstance(new_messages[-1], AssistantMessage)
    assert new_messages[-1].content[0].text == "done"


def test_run_agent_loop_abort_during_tool_does_not_continue_to_next_model_call() -> None:
    from loushang.agent import AbortSignal
    from loushang.agent.agent_loop import run_agent_loop

    signal = AbortSignal()
    emitted: list[dict[str, Any]] = []
    stream_calls = 0

    class AbortingTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            del tool_call_id, params, on_update
            signal.aborted = True
            return AgentToolResult(content=[TextPart(type="text", text="cancelled")], details={})

    async def emit(event):
        emitted.append(event)

    async def stream_fn(model, context: Context, options=None):
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls > 1:
            raise AssertionError("agent loop should not call model again after abort")
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[AbortingTool()])

    new_messages = asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, signal=signal, stream_fn=stream_fn))

    event_types = [event["type"] for event in emitted]
    assert stream_calls == 1
    assert "tool_execution_start" in event_types
    assert "tool_execution_end" not in event_types
    assert event_types[-1] == "agent_end"
    assert [getattr(message, "role", None) for message in new_messages] == ["user", "assistant", "assistant"]
    assert getattr(new_messages[-1], "stop_reason", None) == "aborted"


def test_run_agent_loop_abort_before_drained_follow_up_does_not_consume_follow_up() -> None:
    from loushang.agent import AbortSignal
    from loushang.agent.agent_loop import run_agent_loop

    signal = AbortSignal()
    emitted: list[dict[str, Any]] = []
    stream_calls = 0

    async def emit(event):
        emitted.append(event)

    async def stream_fn(model, context: Context, options=None):
        nonlocal stream_calls
        del model, context, options
        stream_calls += 1
        if stream_calls > 1:
            raise AssertionError("agent loop should not call model again after abort")
        return _stream_with_final_message(_assistant_text_message("first"))

    async def get_follow_up_messages():
        signal.aborted = True
        return [UserMessage(role="user", content="queued follow-up", timestamp=0.0)]

    prompts = [UserMessage(role="user", content="start", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[])
    config = replace(_config(stream_fn), get_follow_up_messages=get_follow_up_messages)

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, signal=signal, stream_fn=stream_fn))

    consumed_user_texts = [
        message.content
        for message in new_messages
        if isinstance(message, UserMessage) and message.content == "queued follow-up"
    ]
    assert consumed_user_texts == []
    assert stream_calls == 1
    assert [getattr(message, "role", None) for message in new_messages] == ["user", "assistant", "assistant"]
    assert getattr(new_messages[-1], "stop_reason", None) == "aborted"


def test_run_agent_loop_steer_then_abort_before_follow_up_does_not_resume_old_task() -> None:
    from loushang.agent import AbortSignal
    from loushang.agent.agent_loop import run_agent_loop

    signal = AbortSignal()
    emitted: list[dict[str, Any]] = []
    stream_user_texts: list[str] = []
    steering_polls = 0
    follow_up_polls = 0

    async def emit(event):
        emitted.append(event)

    async def stream_fn(model, context: Context, options=None):
        del model, options
        last = context.messages[-1]
        if isinstance(last, UserMessage):
            stream_user_texts.append(str(last.content))
        return _stream_with_final_message(_assistant_text_message(f"response {len(stream_user_texts)}"))

    async def get_steering_messages():
        nonlocal steering_polls
        steering_polls += 1
        if steering_polls == 2:
            return [UserMessage(role="user", content="steer current run", timestamp=0.0)]
        return []

    async def get_follow_up_messages():
        nonlocal follow_up_polls
        follow_up_polls += 1
        signal.aborted = True
        return [UserMessage(role="user", content="queued follow-up", timestamp=0.0)]

    prompts = [UserMessage(role="user", content="start", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[])
    config = replace(
        _config(stream_fn),
        get_steering_messages=get_steering_messages,
        get_follow_up_messages=get_follow_up_messages,
    )

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, signal=signal, stream_fn=stream_fn))

    assert stream_user_texts == ["start", "steer current run"]
    assert follow_up_polls == 1
    assert [
        message.content
        for message in new_messages
        if isinstance(message, UserMessage) and message.content == "queued follow-up"
    ] == []
    assert [getattr(message, "role", None) for message in new_messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "assistant",
    ]
    assert getattr(new_messages[-1], "stop_reason", None) == "aborted"


def test_run_agent_loop_abort_before_tool_execution_skips_tool_and_next_model_call() -> None:
    from loushang.agent import AbortSignal
    from loushang.agent.agent_loop import run_agent_loop

    signal = AbortSignal()
    emitted: list[dict[str, Any]] = []
    stream_calls = 0
    executed = False

    class SkippedTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            nonlocal executed
            executed = True
            return await super().execute(tool_call_id, params, signal=signal, on_update=on_update)

    async def emit(event):
        emitted.append(event)

    async def before_tool_call(context, signal):
        signal.aborted = True
        return None

    async def stream_fn(model, context: Context, options=None):
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls > 1:
            raise AssertionError("agent loop should not call model again after abort")
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[SkippedTool()])
    config = replace(_config(stream_fn), before_tool_call=before_tool_call)

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, signal=signal, stream_fn=stream_fn))

    event_types = [event["type"] for event in emitted]
    assert stream_calls == 1
    assert executed is False
    assert "tool_execution_start" in event_types
    assert "tool_execution_end" not in event_types
    assert event_types[-1] == "agent_end"
    assert [getattr(message, "role", None) for message in new_messages] == ["user", "assistant", "assistant"]
    assert getattr(new_messages[-1], "stop_reason", None) == "aborted"


def test_tool_exception_can_project_structured_error_details() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    class StructuredToolError(PermissionError):
        def __init__(self) -> None:
            super().__init__("Tool write requires approval")
            self.tool_result_details = {
                "tool_name": "write",
                "policy_disposition": "ask",
                "policy_code": "tool_requires_approval",
                "approval_required": True,
                "approval_decision": "deny",
            }

    class DeniedTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            del tool_call_id, params, signal, on_update
            raise StructuredToolError()

    emitted: list[dict[str, Any]] = []

    async def emit(event):
        emitted.append(event)

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(
            _assistant_tool_call_message_with_calls(
                [ToolCall(type="toolCall", id="tc_1", name="write", arguments={"x": 1})]
            )
        )

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[DeniedTool(name="write", label="Write")])

    new_messages = asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

    tool_end_event = next(event for event in emitted if event["type"] == "tool_execution_end")
    assert tool_end_event["is_error"] is True
    assert tool_end_event["result"].details == {
        "tool_name": "write",
        "policy_disposition": "ask",
        "policy_code": "tool_requires_approval",
        "approval_required": True,
        "approval_decision": "deny",
    }
    assert getattr(new_messages[2], "role", None) == "toolResult"
    assert new_messages[2].details == tool_end_event["result"].details


def test_run_agent_loop_rejects_tool_arguments_requiring_implicit_conversion_by_default() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    executed: list[dict[str, Any]] = []

    class RecordingTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            del tool_call_id, signal, on_update
            executed.append(params)
            return AgentToolResult(content=[TextPart(type="text", text=str(params["x"] + 1))], details={"value": params["x"] + 1})

    async def emit(event):
        return None

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(
            _assistant_tool_call_message_with_calls(
                [ToolCall(type="toolCall", id="tc_1", name="calc", arguments={"x": "41"})]
            )
        )

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[RecordingTool()])

    new_messages = asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

    assert executed == []
    assert getattr(new_messages[2], "role", None) == "toolResult"
    assert new_messages[2].is_error is True
    assert 'Validation failed for tool "calc":' in new_messages[2].content[0].text
    assert "x: must be an integer" in new_messages[2].content[0].text


def test_tool_execution_update_keeps_raw_arguments_after_prepare_arguments() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    emitted: list[dict[str, Any]] = []
    executed: list[dict[str, Any]] = []

    class AliasTool:
        name = "read"
        description = "read file"
        label = "Read"
        execution_mode = "parallel"

        def __init__(self) -> None:
            self.parameters = {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            }

        def prepare_arguments(self, args: dict[str, Any]) -> dict[str, Any]:
            return {"path": args["file_path"]}

        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            del tool_call_id, signal
            executed.append(params)
            if on_update is not None:
                on_update(AgentToolResult(content=[TextPart(type="text", text="reading")], details={"path": params["path"]}))
            return AgentToolResult(content=[TextPart(type="text", text=params["path"])], details={"path": params["path"]})

    async def emit(event):
        emitted.append(event)

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(
            _assistant_tool_call_message_with_calls(
                [ToolCall(type="toolCall", id="tc_1", name="read", arguments={"file_path": "notes.txt"})]
            )
        )

    prompts = [UserMessage(role="user", content="read", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[AliasTool()])

    new_messages = asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

    start_event = next(event for event in emitted if event["type"] == "tool_execution_start")
    update_event = next(event for event in emitted if event["type"] == "tool_execution_update")

    assert executed == [{"path": "notes.txt"}]
    assert start_event["args"] == {"file_path": "notes.txt"}
    assert update_event["args"] == {"file_path": "notes.txt"}
    assert getattr(new_messages[2], "role", None) == "toolResult"
    assert new_messages[2].content[0].text == "notes.txt"


def test_tool_execution_update_is_emitted_before_tool_execute_returns() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    emitted: list[dict[str, Any]] = []
    event_types_seen_before_return: list[str] = []

    class StreamingTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            del tool_call_id, signal
            if on_update is not None:
                forwarded = on_update(
                    AgentToolResult(
                        content=[TextPart(type="text", text="streaming")],
                        details={"progress": "during-execute"},
                    )
                )
                if inspect.isawaitable(forwarded):
                    await forwarded
            event_types_seen_before_return.extend(event["type"] for event in emitted)
            return AgentToolResult(content=[TextPart(type="text", text=str(params["x"] + 1))], details={"value": params["x"] + 1})

    async def emit(event):
        emitted.append(event)

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[StreamingTool()])

    asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

    assert "tool_execution_update" in event_types_seen_before_return
    assert "tool_execution_end" not in event_types_seen_before_return


def test_run_agent_loop_projects_agent_tools_to_ai_tools_for_model_context() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    async def emit(event):
        return None

    async def stream_fn(model, context: Context, options=None):
        assert context.tools is not None
        assert len(context.tools) == 1
        assert isinstance(context.tools[0], Tool)
        assert context.tools[0] == Tool(
            name="calc",
            description="calculate",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": ["x"],
                "additionalProperties": False,
            },
        )
        return _stream_with_final_message(_assistant_text_message("hello"))

    prompts = [UserMessage(role="user", content="hi", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[FakeTool()])

    new_messages = asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

    assert isinstance(new_messages[-1], AssistantMessage)
    assert new_messages[-1].content[0].text == "hello"


def test_run_agent_loop_continue_rejects_invalid_context() -> None:
    from loushang.agent.agent_loop import run_agent_loop_continue

    async def emit(event):
        raise AssertionError(f"unexpected event: {event}")

    with pytest.raises(ValueError, match="no messages"):
        asyncio.run(run_agent_loop_continue(AgentContext(system_prompt="system", messages=[]), _config(lambda *_: None), emit))

    assistant = _assistant_text_message("hello")
    with pytest.raises(ValueError, match="assistant"):
        asyncio.run(run_agent_loop_continue(AgentContext(system_prompt="system", messages=[assistant]), _config(lambda *_: None), emit))


def test_agent_loop_returns_event_stream_with_result() -> None:
    from loushang.agent.agent_loop import agent_loop

    async def stream_fn(model, context: Context, options=None):
        return _stream_with_final_message(_assistant_text_message("hello"))

    prompts = [UserMessage(role="user", content="hi", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[])

    async def scenario() -> None:
        stream = agent_loop(prompts, context, _config(stream_fn), stream_fn=stream_fn)
        assert isinstance(stream, EventStream)
        events = [event async for event in stream]
        result = await stream.result()

        assert events[-1]["type"] == "agent_end"
        assert len(result) == 2
        assert isinstance(result[-1], AssistantMessage)
        assert result[-1].content[0].text == "hello"

    asyncio.run(scenario())


def test_agent_loop_continue_returns_event_stream_with_result() -> None:
    from loushang.agent.agent_loop import agent_loop_continue

    async def stream_fn(model, context: Context, options=None):
        return _stream_with_final_message(_assistant_text_message("continued"))

    context = AgentContext(
        system_prompt="system",
        messages=[UserMessage(role="user", content="hi", timestamp=0.0)],
    )

    async def scenario() -> None:
        stream = agent_loop_continue(context, _config(stream_fn), stream_fn=stream_fn)
        assert isinstance(stream, EventStream)
        events = [event async for event in stream]
        result = await stream.result()

        assert events[0]["type"] == "agent_start"
        assert events[-1]["type"] == "agent_end"
        assert len(result) == 1
        assert isinstance(result[-1], AssistantMessage)
        assert result[-1].content[0].text == "continued"

    asyncio.run(scenario())


def test_before_tool_call_block_emits_error_tool_result_without_executing_tool() -> None:
    from loushang.agent.agent_loop import run_agent_loop
    from loushang.agent.types import BeforeToolCallResult

    executed = False

    class BlockedTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            nonlocal executed
            executed = True
            return await super().execute(tool_call_id, params, signal=signal, on_update=on_update)

    async def emit(event):
        return None

    async def before_tool_call(context, signal):
        return BeforeToolCallResult(block=True, reason="blocked by policy")

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[BlockedTool()])
    config = _config(stream_fn)
    config = replace(config, before_tool_call=before_tool_call)

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, stream_fn=stream_fn))

    tool_result = new_messages[2]
    assert getattr(tool_result, "role", None) == "toolResult"
    assert tool_result.is_error is True
    assert tool_result.content[0].text == "blocked by policy"
    assert executed is False


def test_before_tool_call_can_rewrite_tool_name_and_arguments() -> None:
    from loushang.agent.agent_loop import run_agent_loop
    from loushang.agent.types import BeforeToolCallResult

    executed: list[tuple[str, dict[str, Any]]] = []

    class RewrittenTool(FakeTool):
        name = "calc_rewritten"

        def __post_init__(self) -> None:
            self.parameters = {
                "type": "object",
                "properties": {"y": {"type": "integer"}},
                "required": ["y"],
                "additionalProperties": False,
            }

        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            executed.append((self.name, params))
            return AgentToolResult(
                content=[TextPart(type="text", text=str(params["y"] + 10))],
                details={"value": params["y"] + 10},
            )

    async def emit(event):
        return None

    async def before_tool_call(context, signal):
        assert context.tool_call.name == "calc"
        assert context.args == {"x": 1}
        return BeforeToolCallResult(tool_name="calc_rewritten", arguments={"y": 2})

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="rewrite tool", timestamp=0.0)]
    context = AgentContext(
        system_prompt="system",
        messages=[],
        tools=[FakeTool(), RewrittenTool(name="calc_rewritten", label="Calc Rewritten")],
    )
    config = _config(stream_fn)
    config = replace(config, before_tool_call=before_tool_call)

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, stream_fn=stream_fn))

    tool_result = new_messages[2]
    assert getattr(tool_result, "role", None) == "toolResult"
    assert tool_result.tool_name == "calc_rewritten"
    assert tool_result.content[0].text == "12"
    assert executed == [("calc_rewritten", {"y": 2})]


def test_after_tool_call_can_override_content_details_and_error_flag() -> None:
    from loushang.agent.agent_loop import run_agent_loop
    from loushang.agent.types import AfterToolCallResult

    async def emit(event):
        return None

    async def after_tool_call(context, signal):
        return AfterToolCallResult(
            content=[TextPart(type="text", text="rewritten")],
            details={"override": True},
            is_error=True,
        )

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[FakeTool()])
    config = _config(stream_fn)
    config = replace(config, after_tool_call=after_tool_call)

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, stream_fn=stream_fn))

    tool_result = new_messages[2]
    assert getattr(tool_result, "role", None) == "toolResult"
    assert tool_result.is_error is True
    assert tool_result.content[0].text == "rewritten"
    assert tool_result.details == {"override": True}


def test_after_tool_call_exception_becomes_error_tool_result() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    async def emit(event):
        return None

    async def after_tool_call(context, signal):
        del context, signal
        raise RuntimeError("after hook exploded")

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[FakeTool()])
    config = replace(_config(stream_fn), after_tool_call=after_tool_call)

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, stream_fn=stream_fn))

    tool_result = new_messages[2]
    assert getattr(tool_result, "role", None) == "toolResult"
    assert tool_result.is_error is True
    assert tool_result.content[0].text == "after hook exploded"
    assert isinstance(new_messages[-1], AssistantMessage)
    assert new_messages[-1].content[0].text == "done"


def test_agent_loop_stops_after_tool_batch_when_all_results_terminate() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    llm_calls = 0

    class TerminatingTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            del tool_call_id, signal, on_update
            return AgentToolResult(
                content=[TextPart(type="text", text=f"terminated: {params['x']}")],
                details={"value": params["x"]},
                terminate=True,
            )

    async def emit(event):
        return None

    async def stream_fn(model, context: Context, options=None):
        nonlocal llm_calls
        llm_calls += 1
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use terminating tool", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[TerminatingTool()])

    new_messages = asyncio.run(run_agent_loop(prompts, context, _config(stream_fn), emit, stream_fn=stream_fn))

    assert llm_calls == 1
    assert [getattr(message, "role", None) for message in new_messages] == ["user", "assistant", "toolResult"]


def test_agent_loop_continues_after_parallel_batch_when_not_all_results_terminate() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    llm_calls = 0

    class SometimesTerminatingTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            del tool_call_id, signal, on_update
            return AgentToolResult(
                content=[TextPart(type="text", text=f"value: {params['x']}")],
                details={"value": params["x"]},
                terminate=params["x"] == 1,
            )

    async def emit(event):
        return None

    async def stream_fn(model, context: Context, options=None):
        nonlocal llm_calls
        llm_calls += 1
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        return _stream_with_final_message(
            _assistant_tool_call_message_with_calls(
                [
                    ToolCall(type="toolCall", id="tc_1", name="calc", arguments={"x": 1}),
                    ToolCall(type="toolCall", id="tc_2", name="calc", arguments={"x": 2}),
                ]
            )
        )

    prompts = [UserMessage(role="user", content="use two tools", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[SometimesTerminatingTool()])
    config = replace(_config(stream_fn), tool_execution="parallel")

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, stream_fn=stream_fn))

    assert llm_calls == 2
    assert [getattr(message, "role", None) for message in new_messages] == [
        "user",
        "assistant",
        "toolResult",
        "toolResult",
        "assistant",
    ]


def test_tool_execution_mode_sequential_forces_sequential_batch() -> None:
    from loushang.agent.agent_loop import run_agent_loop

    release_first = asyncio.Event()
    first_resolved = False
    parallel_observed = False

    class SequentialTool(FakeTool):
        async def execute(self, tool_call_id: str, params: dict[str, Any], signal=None, on_update=None) -> AgentToolResult[dict[str, Any]]:
            nonlocal first_resolved, parallel_observed
            del tool_call_id, signal, on_update
            if params["x"] == 1:
                await release_first.wait()
                first_resolved = True
            if params["x"] == 2 and not first_resolved:
                parallel_observed = True
            return AgentToolResult(
                content=[TextPart(type="text", text=f"value: {params['x']}")],
                details={"value": params["x"]},
            )

    async def emit(event):
        return None

    async def stream_fn(model, context: Context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_text_message("done"))
        asyncio.get_running_loop().call_later(0.02, release_first.set)
        return _stream_with_final_message(
            _assistant_tool_call_message_with_calls(
                [
                    ToolCall(type="toolCall", id="tc_1", name="calc", arguments={"x": 1}),
                    ToolCall(type="toolCall", id="tc_2", name="calc", arguments={"x": 2}),
                ]
            )
        )

    prompts = [UserMessage(role="user", content="use sequential tools", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[SequentialTool(execution_mode="sequential")])
    config = replace(_config(stream_fn), tool_execution="parallel")

    asyncio.run(run_agent_loop(prompts, context, config, emit, stream_fn=stream_fn))

    assert parallel_observed is False


def test_after_tool_call_can_mark_tool_batch_as_terminating() -> None:
    from loushang.agent.agent_loop import run_agent_loop
    from loushang.agent.types import AfterToolCallResult

    llm_calls = 0

    async def emit(event):
        return None

    async def after_tool_call(context, signal):
        del context, signal
        return AfterToolCallResult(terminate=True)

    async def stream_fn(model, context: Context, options=None):
        nonlocal llm_calls
        llm_calls += 1
        return _stream_with_final_message(_assistant_tool_call_message())

    prompts = [UserMessage(role="user", content="use terminating hook", timestamp=0.0)]
    context = AgentContext(system_prompt="system", messages=[], tools=[FakeTool()])
    config = replace(_config(stream_fn), after_tool_call=after_tool_call)

    new_messages = asyncio.run(run_agent_loop(prompts, context, config, emit, stream_fn=stream_fn))

    assert llm_calls == 1
    assert [getattr(message, "role", None) for message in new_messages] == ["user", "assistant", "toolResult"]
