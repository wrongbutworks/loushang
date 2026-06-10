import asyncio

from loushang.ai.event_stream.stream import AssistantMessageEventStream
from loushang.ai.model import Capabilities, Model
from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage


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


def _stream_with_final_message(message: AssistantMessage) -> AssistantMessageEventStream:
    stream = AssistantMessageEventStream()
    stream.push({"type": "start", "partial": message})
    stream.push({"type": "text_start", "content_index": 0, "partial": message})
    stream.push({"type": "text_delta", "content_index": 0, "delta": message.content[0].text, "partial": message})
    stream.push({"type": "text_end", "content_index": 0, "content": message.content[0].text, "partial": message})
    stream.push({"type": "done", "reason": message.stop_reason, "message": message})  # type: ignore[typeddict-item]
    return stream


def _config():
    from loushang.agent.types import AgentLoopConfig

    return AgentLoopConfig(
        model=_model(),
        convert_to_llm=lambda messages: [
            message
            for message in messages
            if isinstance(message, UserMessage) or isinstance(message, AssistantMessage)
        ],
        tool_execution="parallel",
    )


def test_run_agent_collects_events_and_new_messages_for_prompt_run() -> None:
    from loushang.agent.harness import AgentRunSpec, run_agent
    from loushang.agent.types import AgentContext

    async def stream_fn(model, context, options=None):
        assert context.system_prompt == "system"
        assert [getattr(message, "role", None) for message in context.messages] == ["user"]
        return _stream_with_final_message(_assistant_text_message("hello"))

    prompt = UserMessage(role="user", content="hi", timestamp=0.0)
    spec = AgentRunSpec(
        prompts=(prompt,),
        context=AgentContext(system_prompt="system", messages=()),
        config=_config(),
        stream_fn=stream_fn,
    )

    result = asyncio.run(run_agent(spec))

    assert result.status == "completed"
    assert result.error is None
    assert result.stop_reason == "stop"
    assert [event["type"] for event in result.events] == [
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
    assert [getattr(message, "role", None) for message in result.new_messages] == ["user", "assistant"]
    assert result.new_messages[-1].content[0].text == "hello"


def test_run_agent_can_continue_from_existing_context() -> None:
    from loushang.agent.harness import AgentRunSpec, run_agent
    from loushang.agent.types import AgentContext

    async def stream_fn(model, context, options=None):
        assert [getattr(message, "role", None) for message in context.messages] == ["user"]
        return _stream_with_final_message(_assistant_text_message("continued"))

    context = AgentContext(
        system_prompt="system",
        messages=(UserMessage(role="user", content="continue", timestamp=0.0),),
    )
    spec = AgentRunSpec(
        mode="continue",
        context=context,
        config=_config(),
        stream_fn=stream_fn,
    )

    result = asyncio.run(run_agent(spec))

    assert result.status == "completed"
    assert [getattr(message, "role", None) for message in result.new_messages] == ["assistant"]
    assert result.new_messages[-1].content[0].text == "continued"


def test_run_agent_returns_failed_result_when_loop_raises() -> None:
    from loushang.agent.harness import AgentRunSpec, run_agent
    from loushang.agent.types import AgentContext

    async def stream_fn(model, context, options=None):
        raise RuntimeError("provider unavailable")

    spec = AgentRunSpec(
        prompts=(UserMessage(role="user", content="hi", timestamp=0.0),),
        context=AgentContext(system_prompt="system", messages=()),
        config=_config(),
        stream_fn=stream_fn,
    )

    result = asyncio.run(run_agent(spec))

    assert result.status == "failed"
    assert isinstance(result.error, RuntimeError)
    assert str(result.error) == "provider unavailable"
    assert [event["type"] for event in result.events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
    ]
    assert result.new_messages == ()
