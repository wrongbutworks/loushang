"""Portable JSONL branch export for the optional Agent transcript profile."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from loushang.harness.agent_transcript.file_store import write_agent_transcript_file
from loushang.harness.agent_transcript.types import AgentTranscriptRecord
from loushang.harness.conversation import ConversationHeader


def export_agent_transcript_to_jsonl(
    header: ConversationHeader,
    branch_entries: Sequence[AgentTranscriptRecord],
    output_path: str | Path,
) -> str:
    """Write the selected branch as a standalone linear current-Native transcript."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_agent_transcript_file(
        path, header, linearize_agent_transcript_branch(branch_entries)
    )
    return str(path)


def linearize_agent_transcript_branch(
    entries: Sequence[AgentTranscriptRecord],
) -> list[AgentTranscriptRecord]:
    """Preserve record IDs while making an exported branch independently readable."""

    linear_entries: list[AgentTranscriptRecord] = []
    previous_id: str | None = None
    for entry in entries:
        linear_entries.append(replace(entry, parent_id=previous_id))
        previous_id = entry.record_id
    return linear_entries
