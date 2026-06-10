from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loushang.agent.types import (
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    StreamFn,
)

AgentRunMode = Literal["prompt", "continue"]
AgentRunStatus = Literal["completed", "failed"]


@dataclass(frozen=True, kw_only=True)
class AgentRunSpec:
    context: AgentContext
    config: AgentLoopConfig
    prompts: tuple[AgentMessage, ...] = ()
    mode: AgentRunMode = "prompt"
    signal: object | None = None
    stream_fn: StreamFn | None = None


@dataclass(frozen=True)
class AgentRunResult:
    status: AgentRunStatus
    new_messages: tuple[AgentMessage, ...] = ()
    events: tuple[AgentEvent, ...] = ()
    stop_reason: str | None = None
    error: Exception | None = None
