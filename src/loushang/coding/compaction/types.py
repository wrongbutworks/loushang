from __future__ import annotations

from dataclasses import dataclass

from loushang.agent import AgentMessage
from loushang.harness.agent_transcript import (
    CompactionPlan as CompactionPlan,
)
from loushang.harness.agent_transcript import (
    CompactionPreparation as CompactionPreparation,
)
from loushang.harness.agent_transcript import (
    CompactionResult as CompactionResult,
)
from loushang.harness.agent_transcript import (
    CompactionStatus as CompactionStatus,
)
from loushang.harness.context.usage import ContextUsageEstimate as ContextUsageEstimate


@dataclass(frozen=True)
class BranchSummaryResult:
    summary: str | None = None
    details: object | None = None
    aborted: bool = False
    error: str | None = None


@dataclass(frozen=True)
class BranchSummaryDetails:
    read_files: list[str]
    modified_files: list[str]


@dataclass(frozen=True)
class BranchPreparation:
    messages: list[AgentMessage]
    entry_ids: list[str]
    total_tokens: int


@dataclass(frozen=True)
class CollectEntriesResult:
    entries: list[object]
    common_ancestor_id: str | None
