from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class SessionMetadata:
    created_at: str
    updated_at: str
    name: str | None = None


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    cwd: str
    session_file: Path | None
    parent_session: str | None
    leaf_id: str | None
    metadata: SessionMetadata


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    cwd: str
    session_file: Path | None
    parent_session: str | None
    leaf_id: str | None
    created_at: str
    updated_at: str
    name: str | None
    message_count: int
    entry_count: int
    first_message: str
    all_messages_text: str
    last_message_preview: str | None
    model: dict[str, str] | None
    has_diagnostics: bool = False
    diagnostic_count: int = 0
    last_diagnostic_code: str | None = None
    last_diagnostic_level: str | None = None


@dataclass(frozen=True, kw_only=True)
class SessionQuery:
    cwd: str | None = None
    name: str | None = None
    parent_session: str | None = None
    text: str | None = None
    named: bool | None = None
    sort_by: Literal["recent", "relevance"] = "recent"
    has_diagnostics: bool | None = None
    limit: int | None = None
