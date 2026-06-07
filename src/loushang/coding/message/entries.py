from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from loushang.agent import AgentMessage
from loushang.ai.types import ImagePart, TextPart

ContentBlock: TypeAlias = TextPart | ImagePart


@dataclass(frozen=True)
class SessionHeader:
    type: str
    version: int
    id: str
    timestamp: str
    cwd: str
    parent_session: str | None = None


@dataclass(frozen=True)
class SessionEntryBase:
    type: str
    id: str
    parent_id: str | None
    timestamp: str


@dataclass(frozen=True)
class SessionMessageEntry(SessionEntryBase):
    message: AgentMessage


@dataclass(frozen=True)
class ThinkingLevelChangeEntry(SessionEntryBase):
    thinking_level: str


@dataclass(frozen=True)
class ModelChangeEntry(SessionEntryBase):
    provider: str
    model_id: str


@dataclass(frozen=True)
class CompactionEntry(SessionEntryBase):
    summary: str
    first_kept_entry_id: str
    tokens_before: int
    details: object | None = None
    from_hook: bool | None = None


@dataclass(frozen=True)
class BranchSummaryEntry(SessionEntryBase):
    from_id: str
    summary: str
    details: object | None = None
    from_hook: bool | None = None


@dataclass(frozen=True)
class CustomEntry(SessionEntryBase):
    custom_type: str
    data: object | None = None


@dataclass(frozen=True)
class CustomMessageEntry(SessionEntryBase):
    custom_type: str
    content: str | list[ContentBlock]
    details: object | None = None
    display: bool = True


@dataclass(frozen=True)
class LabelEntry(SessionEntryBase):
    target_id: str
    label: str | None


@dataclass(frozen=True)
class SessionInfoEntry(SessionEntryBase):
    name: str | None = None


SessionEntry: TypeAlias = (
    SessionMessageEntry
    | ThinkingLevelChangeEntry
    | ModelChangeEntry
    | CompactionEntry
    | BranchSummaryEntry
    | CustomEntry
    | CustomMessageEntry
    | LabelEntry
    | SessionInfoEntry
)


@dataclass(frozen=True)
class SessionContext:
    messages: list[AgentMessage] = field(default_factory=list)
    thinking_level: str = "off"
    model: dict[str, str] | None = None


@dataclass(frozen=True)
class SessionTreeNode:
    entry: SessionEntry
    children: list[SessionTreeNode] = field(default_factory=list)
    label: str | None = None
    label_timestamp: str | None = None
