"""Compatibility exports for the Harness Native transcript file store."""

from loushang.harness.agent_transcript.file_store import (
    AgentTranscriptFileLayout,
    create_agent_transcript_file_store,
)

CodingSessionFileLayout = AgentTranscriptFileLayout
create_coding_file_store = create_agent_transcript_file_store

__all__ = ["CodingSessionFileLayout", "create_coding_file_store"]
