from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loushang.harness.agent_transcript import write_agent_transcript_file

if TYPE_CHECKING:
    from loushang.coding.session.agent_session import AgentSession


def export_session_to_jsonl(session: AgentSession, output_path: str | None = None) -> str:
    path = (
        Path(output_path)
        if output_path is not None
        else _default_export_path(session)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_agent_transcript_file(
        path,
        session.session_manager.header,
        _linearize_branch(session.session_manager.get_branch()),
    )
    return str(path)


def _default_export_path(session: AgentSession) -> Path:
    cwd = Path(session.session_manager.get_cwd()).expanduser().resolve()
    timestamp = (
        datetime.now(UTC)
        .isoformat()
        .replace("+00:00", "Z")
        .replace(":", "-")
        .replace(".", "-")
    )
    return cwd / f"session-{timestamp}.jsonl"


def _linearize_branch(entries):
    linear_entries = []
    previous_id: str | None = None
    for entry in entries:
        linear_entries.append(replace(entry, parent_id=previous_id))
        previous_id = entry.record_id
    return linear_entries
