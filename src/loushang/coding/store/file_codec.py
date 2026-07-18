"""Compatibility exports for the Harness Native transcript file provider."""

from loushang.harness.agent_transcript.file_store import (
    AgentTranscriptFileError,
    agent_transcript_journal,
    append_agent_transcript_record,
    create_agent_transcript_repository,
    load_agent_transcript_file,
    load_agent_transcript_repository,
    load_current_agent_transcript_header,
    write_agent_transcript_file,
)

SessionFileError = AgentTranscriptFileError
session_journal = agent_transcript_journal
append_session_entry = append_agent_transcript_record
create_session_repository = create_agent_transcript_repository
load_session_file = load_agent_transcript_file
load_session_repository = load_agent_transcript_repository
load_current_session_header = load_current_agent_transcript_header
write_session_file = write_agent_transcript_file

__all__ = [
    "SessionFileError",
    "append_session_entry",
    "create_session_repository",
    "load_current_session_header",
    "load_session_file",
    "load_session_repository",
    "session_journal",
    "write_session_file",
]
