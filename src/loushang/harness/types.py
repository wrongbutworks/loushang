from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

AgentRunMode = Literal["prompt", "continue"]
AgentRunStatus = Literal["completed", "failed"]
AgentEventSink = Callable[["AgentEvent"], Awaitable[None] | None]


@dataclass(frozen=True, kw_only=True)
class AgentRunSpec:
    context: AgentContext
    config: AgentLoopConfig
    prompts: tuple[AgentMessage, ...] = ()
    mode: AgentRunMode = "prompt"
    signal: object | None = None
    stream_fn: StreamFn | None = None
    event_sink: AgentEventSink | None = None


@dataclass(frozen=True)
class AgentRunResult:
    status: AgentRunStatus
    new_messages: tuple[AgentMessage, ...] = ()
    events: tuple[AgentEvent, ...] = ()
    stop_reason: str | None = None
    error: Exception | None = None


from loushang.agent.types import (  # noqa: E402
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    StreamFn,
)
