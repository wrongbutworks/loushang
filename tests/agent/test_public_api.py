from dataclasses import is_dataclass
from typing import get_args

from loushang.agent import (
    AfterToolCallContext,
    AfterToolCallResult,
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentOptions,
    AgentState,
    AgentToolResult,
    BeforeToolCallContext,
    BeforeToolCallResult,
    ProxyAssistantMessageEvent,
    ProxyStreamOptions,
    ThinkingLevel,
    ToolExecutionMode,
    agent_loop,
    agent_loop_continue,
    stream_proxy,
)
from loushang.ai.model import Capabilities, Model
from loushang.ai.types import UserMessage


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


def test_public_types_are_exported() -> None:
    assert isinstance(
        AgentState(system_prompt="", model=_model(), thinking_level="off"), AgentState
    )
    assert is_dataclass(AgentContext)
    assert is_dataclass(AgentLoopConfig)
    assert is_dataclass(AgentOptions)
    assert is_dataclass(AgentToolResult)
    assert is_dataclass(ProxyStreamOptions)
    assert BeforeToolCallResult.__annotations__["block"] == "bool | None"
    assert AfterToolCallResult.__annotations__["is_error"] == "bool | None"
    assert AfterToolCallResult.__annotations__["terminate"] == "bool | None"
    assert AgentToolResult(content=[], details={}).terminate is False


def test_public_literal_and_union_types_are_defined() -> None:
    assert set(get_args(ToolExecutionMode)) == {"sequential", "parallel"}
    assert set(get_args(ThinkingLevel)) == {
        "off",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
    }
    assert get_args(AgentMessage)
    assert get_args(AgentEvent)
    assert get_args(ProxyAssistantMessageEvent)


def test_hook_contexts_reference_agent_types() -> None:
    before_annotations = BeforeToolCallContext.__annotations__
    after_annotations = AfterToolCallContext.__annotations__

    assert before_annotations["context"] == "AgentContext"
    assert after_annotations["context"] == "AgentContext"


def test_stream_proxy_is_exported() -> None:
    assert callable(stream_proxy)


def test_agent_loop_facades_are_exported() -> None:
    assert callable(agent_loop)
    assert callable(agent_loop_continue)


def test_agent_state_setters_copy_top_level_messages_and_tools_lists() -> None:
    state = AgentState(system_prompt="", model=_model(), thinking_level="off")
    original_message = UserMessage(role="user", content="hi", timestamp=0.0)
    original_messages = [original_message]
    original_tools = [{"name": "demo"}]

    state.set_messages(original_messages)
    state.set_tools(original_tools)

    original_messages.append(UserMessage(role="user", content="later", timestamp=1.0))
    original_tools.append({"name": "late-tool"})

    assert state.messages == [original_message]
    assert state.tools == [{"name": "demo"}]


def test_agent_state_getters_expose_live_messages_and_tools_lists() -> None:
    state = AgentState(system_prompt="", model=_model(), thinking_level="off")
    message = UserMessage(role="user", content="hi", timestamp=0.0)
    tool = {"name": "demo"}

    live_messages = state.messages
    live_tools = state.tools
    live_messages.append(message)
    live_tools.append(tool)

    assert state.messages[-1] is message
    assert state.tools[-1] is tool
