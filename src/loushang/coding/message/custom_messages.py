from __future__ import annotations

from dataclasses import dataclass

from loushang.agent import CustomAgentMessage
from loushang.ai.types import ImagePart, TextPart

ContentBlock = TextPart | ImagePart


@dataclass(frozen=True)
class BashExecutionMessage(CustomAgentMessage):
    role: str
    command: str
    output: str
    exit_code: int | None
    cancelled: bool
    truncated: bool
    full_output_path: str | None
    timestamp: float
    exclude_from_context: bool = False


@dataclass(frozen=True)
class CustomMessage(CustomAgentMessage):
    role: str
    custom_type: str
    content: str | list[ContentBlock]
    display: bool
    details: object | None
    timestamp: float


@dataclass(frozen=True)
class BranchSummaryMessage(CustomAgentMessage):
    role: str
    summary: str
    from_id: str
    timestamp: float


@dataclass(frozen=True)
class CompactionSummaryMessage(CustomAgentMessage):
    role: str
    summary: str
    tokens_before: int
    timestamp: float
