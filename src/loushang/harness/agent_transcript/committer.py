from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loushang.harness.agent_transcript.codecs import (
    STANDARD_PAYLOAD_VERSION,
    create_agent_transcript_payload_registry,
)
from loushang.harness.agent_transcript.kinds import APPLICATION_MESSAGE_KIND
from loushang.harness.agent_transcript.types import ApplicationMessage
from loushang.harness.agent_transcript.writer import AgentTranscriptWriter
from loushang.protocol import dump_json_value


class ApplicationMessageIdentityConflictError(ValueError):
    pass


@dataclass(frozen=True)
class CommitResult:
    record_id: str
    disposition: Literal["committed", "already_committed"]


@dataclass(frozen=True)
class _CommittedApplicationMessage:
    record_id: str
    fingerprint: str


class TranscriptCommitter:
    """Own the process-local idempotent commit of application messages."""

    def __init__(self, writer: AgentTranscriptWriter) -> None:
        self._writer = writer
        self._committed: dict[str, _CommittedApplicationMessage] = {}
        self._payload_codecs = create_agent_transcript_payload_registry()

    def commit_application_message(
        self,
        message: ApplicationMessage,
    ) -> CommitResult:
        fingerprint = self._fingerprint(message)
        existing = self._committed.get(message.application_message_id)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise ApplicationMessageIdentityConflictError(
                    "application message id was reused with a different payload: "
                    f"{message.application_message_id}"
                )
            return CommitResult(
                record_id=existing.record_id,
                disposition="already_committed",
            )

        record = self._writer.append_application_message(message)
        self._committed[message.application_message_id] = _CommittedApplicationMessage(
            record_id=record.record_id,
            fingerprint=fingerprint,
        )
        return CommitResult(record_id=record.record_id, disposition="committed")

    def _fingerprint(self, message: ApplicationMessage) -> str:
        payload = self._payload_codecs.encode(
            APPLICATION_MESSAGE_KIND,
            STANDARD_PAYLOAD_VERSION,
            message,
        )
        return dump_json_value(
            payload,
            name="application message identity",
            ensure_ascii=False,
            sort_keys=True,
        )


__all__ = [
    "ApplicationMessageIdentityConflictError",
    "CommitResult",
    "TranscriptCommitter",
]
