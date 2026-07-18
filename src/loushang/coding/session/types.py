from __future__ import annotations

from dataclasses import dataclass

from loushang.ai.model import ModelSelection
from loushang.coding.commands import CommandSourceInfo, SessionCommandDescriptor
from loushang.harness.agent_transcript import CompactionDecision, ContextUsageSnapshot
from loushang.harness.agent_transcript import (
    TranscriptNavigationResult as TreeNavigationResult,
)
from loushang.harness.host.types import RunState as RunState
from loushang.harness.session.inspection import (
    AgentSessionState,
    ContextUsage,
    SessionStats,
    TokenUsageTotals,
)


@dataclass(frozen=True)
class CommandExecutionResult:
    invocation_name: str
    result: object | None = None


__all__ = [
    "AgentSessionState",
    "CompactionDecision",
    "CommandExecutionResult",
    "CommandSourceInfo",
    "ContextUsage",
    "ContextUsageSnapshot",
    "ModelSelection",
    "RunState",
    "SessionCommandDescriptor",
    "SessionStats",
    "TokenUsageTotals",
    "TreeNavigationResult",
]
