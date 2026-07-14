from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from loushang.agent import CustomAgentMessage
from loushang.ai.types import ImagePart, TextPart
from loushang.harness.conversation import CommandExecutionRecord

ContentBlock = TextPart | ImagePart


@dataclass(frozen=True, init=False)
class BashExecutionMessage(CommandExecutionRecord, CustomAgentMessage):
    __match_args__ = (
        "role",
        "command",
        "output",
        "exit_code",
        "cancelled",
        "truncated",
        "full_output_path",
        "timestamp",
        "exclude_from_context",
    )

    role: str
    timestamp: float

    def __init__(
        self,
        role: str,
        command: str,
        output: str,
        exit_code: int | None,
        cancelled: bool,
        truncated: bool,
        full_output_path: str | None,
        timestamp: float,
        exclude_from_context: bool = False,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        CommandExecutionRecord.__init__(
            self,
            command=command,
            output=output,
            exit_code=exit_code,
            cancelled=cancelled,
            truncated=truncated,
            full_output_path=full_output_path,
            exclude_from_context=exclude_from_context,
            metadata={} if metadata is None else metadata,
        )
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "timestamp", timestamp)


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
