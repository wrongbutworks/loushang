"""Compatibility exports for Native transcript file locking."""

from loushang.harness.agent_transcript.file_store import (
    LockMode,
    agent_transcript_file_lock,
)

session_file_lock = agent_transcript_file_lock

__all__ = ["LockMode", "session_file_lock"]
