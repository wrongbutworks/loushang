from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import (
    Any,
    Generic,
    Literal,
    NotRequired,
    Protocol,
    TypeAlias,
    TypedDict,
    TypeVar,
    cast,
    runtime_checkable,
)

from loushang.ai.event_stream.stream import AssistantMessageEventStream
from loushang.ai.model import Model
from loushang.ai.options import (
    CallOptions,
    ReasoningOptions,
)
from loushang.ai.types import (
    AssistantMessage,
    AssistantMessageEvent,
    Context,
    ImagePart,
    Message,
    TextPart,
    ToolCall,
    ToolResultMessage,
    Usage,
)

TDetails = TypeVar("TDetails")

ToolExecutionMode: TypeAlias = Literal["sequential", "parallel"]
ThinkingLevel: TypeAlias = Literal["off", "minimal", "low", "medium", "high", "xhigh"]
AgentToolCall: TypeAlias = ToolCall


class AgentThinkingBudgetMap(TypedDict, total=False):
    minimal: int
    low: int
    medium: int
    high: int


@dataclass(frozen=True)
class BeforeToolCallResult:
    block: bool | None = None
    reason: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None


@dataclass(frozen=True)
class AfterToolCallResult:
    content: list[TextPart | ImagePart] | None = None
    details: object | None = None
    is_error: bool | None = None
    terminate: bool | None = None


class CustomAgentMessage:
    """
    Python equivalent of pi-agent's extensible CustomAgentMessages surface.

    Apps should subclass this base type to introduce custom agent-level messages.
    """


AgentMessage: TypeAlias = Message | CustomAgentMessage


@dataclass(frozen=True)
class AgentToolResult(Generic[TDetails]):
    content: list[TextPart | ImagePart]
    details: TDetails
    terminate: bool = False


class AgentToolUpdateCallback(Protocol[TDetails]):
    def __call__(
        self, partial_result: AgentToolResult[TDetails]
    ) -> Awaitable[None] | None: ...


@runtime_checkable
class StreamFn(Protocol):
    def __call__(
        self,
        model: Model,
        context: Context,
        options: CallOptions | None = None,
    ) -> AssistantMessageEventStream | Awaitable[AssistantMessageEventStream]: ...


class ConvertToLlmFn(Protocol):
    def __call__(
        self, messages: list[AgentMessage]
    ) -> list[Message] | Awaitable[list[Message]]: ...


class TransformContextFn(Protocol):
    def __call__(
        self, messages: list[AgentMessage], signal: object | None = None
    ) -> Awaitable[list[AgentMessage]]: ...


class GetApiKeyFn(Protocol):
    def __call__(self, provider: str) -> str | None | Awaitable[str | None]: ...


@runtime_checkable
class AgentTool(Protocol[TDetails]):
    name: str
    description: str
    parameters: dict[str, Any]
    label: str
    prepare_arguments: Callable[[object], dict[str, Any]] | None
    execution_mode: ToolExecutionMode

    def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        signal: object | None = None,
        on_update: AgentToolUpdateCallback[TDetails] | None = None,
    ) -> Awaitable[AgentToolResult[TDetails]]: ...


class _AgentToolWithDefaultExecutionMode(Generic[TDetails]):
    execution_mode: ToolExecutionMode = "parallel"

    def __init__(self, tool: object) -> None:
        self._tool = tool

    @property
    def name(self) -> str:
        return cast(str, getattr(self._tool, "name"))

    @property
    def description(self) -> str:
        return cast(str, getattr(self._tool, "description"))

    @property
    def parameters(self) -> dict[str, Any]:
        return cast(dict[str, Any], getattr(self._tool, "parameters"))

    @property
    def label(self) -> str:
        return cast(str, getattr(self._tool, "label"))

    @property
    def prepare_arguments(self) -> Callable[[object], dict[str, Any]] | None:
        return cast(
            Callable[[object], dict[str, Any]] | None,
            getattr(self._tool, "prepare_arguments", None),
        )

    async def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        signal: object | None = None,
        on_update: AgentToolUpdateCallback[TDetails] | None = None,
    ) -> AgentToolResult[TDetails]:
        execute = cast(AgentTool[TDetails], self._tool).execute
        return await execute(tool_call_id, params, signal, on_update)


def is_agent_tool_like(tool: object) -> bool:
    return all(
        hasattr(tool, field_name)
        for field_name in ("name", "description", "parameters", "label")
    ) and callable(getattr(tool, "execute", None))


def ensure_agent_tool(tool: AgentTool[TDetails] | object) -> AgentTool[Any]:
    if isinstance(tool, AgentTool):
        return tool
    if is_agent_tool_like(tool):
        return _AgentToolWithDefaultExecutionMode(tool)
    raise TypeError(
        "Agent tools must define name, description, parameters, label, execute, and optional execution_mode"
    )


def normalize_agent_tools(
    tools: list[AgentTool[Any]] | None,
) -> list[AgentTool[Any]] | None:
    if tools is None:
        return None
    return [
        ensure_agent_tool(tool)
        if is_agent_tool_like(tool)
        else cast(AgentTool[Any], tool)
        for tool in tools
    ]


@dataclass(frozen=True)
class AgentContext:
    system_prompt: str
    messages: list[AgentMessage] = field(default_factory=list)
    tools: list[AgentTool[Any]] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", normalize_agent_tools(self.tools))


@dataclass(frozen=True)
class BeforeToolCallContext:
    assistant_message: AssistantMessage
    tool_call: AgentToolCall
    args: object
    context: AgentContext


@dataclass(frozen=True)
class AfterToolCallContext:
    assistant_message: AssistantMessage
    tool_call: AgentToolCall
    args: object
    result: AgentToolResult[Any]
    is_error: bool
    context: AgentContext


@dataclass(frozen=True, kw_only=True)
class AgentLoopConfig:
    model: Model
    convert_to_llm: ConvertToLlmFn
    call_options: CallOptions = field(default_factory=CallOptions)
    transform_context: TransformContextFn | None = None
    get_api_key: GetApiKeyFn | None = None
    get_steering_messages: Callable[[], Awaitable[list[AgentMessage]]] | None = None
    get_follow_up_messages: Callable[[], Awaitable[list[AgentMessage]]] | None = None
    tool_execution: ToolExecutionMode = "parallel"
    before_tool_call: (
        Callable[
            [BeforeToolCallContext, object | None],
            Awaitable[BeforeToolCallResult | None],
        ]
        | None
    ) = None
    after_tool_call: (
        Callable[
            [AfterToolCallContext, object | None], Awaitable[AfterToolCallResult | None]
        ]
        | None
    ) = None


class AgentState:
    """
    Mutable runtime state for Agent.

    Contract for `messages` and `tools`:
    - getters return the live internal lists
    - whole-list replacement must go through `set_messages()` / `set_tools()`
    - `set_*()` copies the top-level list
    - incremental mutations on the returned lists (for example `append()` or `clear()`)
      intentionally mutate the current agent state
    """

    def __init__(
        self,
        system_prompt: str,
        model: Model,
        thinking_level: ThinkingLevel,
        tools: list[AgentTool[Any]] | None = None,
        messages: list[AgentMessage] | None = None,
        is_streaming: bool = False,
        streaming_message: AgentMessage | None = None,
        pending_tool_calls: set[str] | None = None,
        error_message: str | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.model = model
        self.thinking_level = thinking_level
        self._tools = list(normalize_agent_tools(tools) or [])
        self._messages = list(messages or [])
        self.is_streaming = is_streaming
        self.streaming_message = streaming_message
        self.pending_tool_calls = set(pending_tool_calls or set())
        self.error_message = error_message

    @property
    def tools(self) -> list[AgentTool[Any]]:
        return self._tools

    @property
    def messages(self) -> list[AgentMessage]:
        return self._messages

    def set_tools(self, tools: list[AgentTool[Any]]) -> None:
        """Replace the tools list, copying the top-level container."""
        self._tools = list(normalize_agent_tools(tools) or [])

    def set_messages(self, messages: list[AgentMessage]) -> None:
        """Replace the messages list, copying the top-level container."""
        self._messages = list(messages)


@dataclass(frozen=True)
class AgentOptions:
    initial_state: AgentState | dict[str, Any] | object | None = None
    convert_to_llm: ConvertToLlmFn | None = None
    transform_context: TransformContextFn | None = None
    stream_fn: StreamFn | None = None
    get_api_key: GetApiKeyFn | None = None
    before_tool_call: (
        Callable[
            [BeforeToolCallContext, object | None],
            Awaitable[BeforeToolCallResult | None],
        ]
        | None
    ) = None
    after_tool_call: (
        Callable[
            [AfterToolCallContext, object | None], Awaitable[AfterToolCallResult | None]
        ]
        | None
    ) = None
    steering_mode: Literal["all", "one-at-a-time"] = "one-at-a-time"
    follow_up_mode: Literal["all", "one-at-a-time"] = "one-at-a-time"
    session_id: str | None = None
    thinking_budgets: AgentThinkingBudgetMap | None = None
    max_retry_delay_ms: int | None = None
    tool_execution: ToolExecutionMode = "parallel"


class AgentStartEvent(TypedDict):
    type: Literal["agent_start"]


class AgentEndEvent(TypedDict):
    type: Literal["agent_end"]
    messages: list[AgentMessage]


class TurnStartEvent(TypedDict):
    type: Literal["turn_start"]


class TurnEndEvent(TypedDict):
    type: Literal["turn_end"]
    message: AgentMessage
    tool_results: list[ToolResultMessage]


class MessageStartEvent(TypedDict):
    type: Literal["message_start"]
    message: AgentMessage


class MessageUpdateEvent(TypedDict):
    type: Literal["message_update"]
    message: AgentMessage
    assistant_message_event: AssistantMessageEvent


class MessageEndEvent(TypedDict):
    type: Literal["message_end"]
    message: AgentMessage


class ToolExecutionStartEvent(TypedDict):
    type: Literal["tool_execution_start"]
    tool_call_id: str
    tool_name: str
    args: object


class ToolExecutionUpdateEvent(TypedDict):
    type: Literal["tool_execution_update"]
    tool_call_id: str
    tool_name: str
    args: object
    partial_result: object


class ToolExecutionEndEvent(TypedDict):
    type: Literal["tool_execution_end"]
    tool_call_id: str
    tool_name: str
    result: object
    is_error: bool
    duration_ms: NotRequired[int]


AgentEvent: TypeAlias = (
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionUpdateEvent
    | ToolExecutionEndEvent
)


class ProxyStartEvent(TypedDict):
    type: Literal["start"]


class ProxyTextStartEvent(TypedDict):
    type: Literal["text_start"]
    content_index: int


class ProxyTextDeltaEvent(TypedDict):
    type: Literal["text_delta"]
    content_index: int
    delta: str


class ProxyTextEndEvent(TypedDict):
    type: Literal["text_end"]
    content_index: int
    content_signature: NotRequired[str]


class ProxyThinkingStartEvent(TypedDict):
    type: Literal["thinking_start"]
    content_index: int


class ProxyThinkingDeltaEvent(TypedDict):
    type: Literal["thinking_delta"]
    content_index: int
    delta: str


class ProxyThinkingEndEvent(TypedDict):
    type: Literal["thinking_end"]
    content_index: int
    content_signature: NotRequired[str]


class ProxyToolCallStartEvent(TypedDict):
    type: Literal["toolcall_start"]
    content_index: int
    id: str
    tool_name: str


class ProxyToolCallDeltaEvent(TypedDict):
    type: Literal["toolcall_delta"]
    content_index: int
    delta: str


class ProxyToolCallEndEvent(TypedDict):
    type: Literal["toolcall_end"]
    content_index: int


class ProxyDoneEvent(TypedDict):
    type: Literal["done"]
    reason: Literal["stop", "length", "toolUse"]
    usage: Usage


class ProxyErrorEvent(TypedDict):
    type: Literal["error"]
    reason: Literal["aborted", "error"]
    usage: Usage
    error_message: NotRequired[str]


ProxyAssistantMessageEvent: TypeAlias = (
    ProxyStartEvent
    | ProxyTextStartEvent
    | ProxyTextDeltaEvent
    | ProxyTextEndEvent
    | ProxyThinkingStartEvent
    | ProxyThinkingDeltaEvent
    | ProxyThinkingEndEvent
    | ProxyToolCallStartEvent
    | ProxyToolCallDeltaEvent
    | ProxyToolCallEndEvent
    | ProxyDoneEvent
    | ProxyErrorEvent
)


@dataclass(frozen=True, kw_only=True)
class ProxyStreamOptions:
    signal: object | None = None
    max_output_tokens: int | None = None
    temperature: float | int | None = None
    reasoning: ReasoningOptions | None = None
    auth_token: str
    proxy_url: str
    max_tokens: int | None = None


__all__ = [
    "AfterToolCallContext",
    "AfterToolCallResult",
    "AgentContext",
    "AgentEvent",
    "AgentLoopConfig",
    "AgentMessage",
    "AgentOptions",
    "AgentState",
    "AgentThinkingBudgetMap",
    "AgentTool",
    "AgentToolCall",
    "AgentToolResult",
    "AgentToolUpdateCallback",
    "BeforeToolCallContext",
    "BeforeToolCallResult",
    "ConvertToLlmFn",
    "CustomAgentMessage",
    "GetApiKeyFn",
    "ProxyAssistantMessageEvent",
    "ProxyStreamOptions",
    "StreamFn",
    "ThinkingLevel",
    "ToolExecutionMode",
    "TransformContextFn",
]
