from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from loushang.ai.types import Message
from loushang.harness.agent_transcript.codecs import STANDARD_PAYLOAD_VERSION
from loushang.harness.agent_transcript.kinds import (
    AGENT_MESSAGE_KIND,
    APPLICATION_MESSAGE_KIND,
    COMMAND_EXECUTION_KIND,
    CONTEXT_BRANCH_SUMMARY_KIND,
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
    CONVERSATION_METADATA_PATCH_KIND,
    EXTENSION_DATA_KIND,
    MODEL_SELECTION_KIND,
    RECORD_ANNOTATION_PATCH_KIND,
    THINKING_SELECTION_KIND,
)
from loushang.harness.agent_transcript.types import (
    AgentTranscriptPayload,
    AgentTranscriptRecord,
    ApplicationMessage,
    BranchContextSummary,
    ContextCompactionCheckpoint,
    ConversationMetadataPatch,
    ExtensionData,
    ModelSelectionSnapshot,
    RecordAnnotationPatch,
    ThinkingSelectionSnapshot,
)
from loushang.harness.conversation.repository import ConversationRepository
from loushang.harness.conversation.types import (
    CommandExecutionRecord,
    ConversationHeader,
    ConversationRecord,
)
from loushang.protocol import JSONValue

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


class AgentTranscriptWriter:
    """Append typed Agent transcript records to the repository's current leaf."""

    def __init__(
        self,
        repository: ConversationRepository[
            ConversationHeader,
            AgentTranscriptRecord,
        ],
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or _utc_now
        self._id_factory = id_factory or _uuid

    @property
    def repository(
        self,
    ) -> ConversationRepository[ConversationHeader, AgentTranscriptRecord]:
        return self._repository

    def append(
        self,
        kind: str,
        payload: AgentTranscriptPayload,
        *,
        payload_version: int = STANDARD_PAYLOAD_VERSION,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        record_id = self._id_factory()
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError("transcript record id factory must return non-empty text")
        created_at = _encode_timestamp(self._clock())
        record = ConversationRecord(
            record_id=record_id,
            parent_id=self._repository.leaf_id,
            kind=kind,
            payload_version=payload_version,
            created_at=created_at,
            payload=payload,
            metadata={} if metadata is None else metadata,
        )
        self._repository.append(cast(AgentTranscriptRecord, record))
        return cast(AgentTranscriptRecord, record)

    def append_agent_message(
        self,
        message: Message,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(AGENT_MESSAGE_KIND, message, metadata=metadata)

    def append_thinking_selection(
        self,
        selection: ThinkingSelectionSnapshot,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(THINKING_SELECTION_KIND, selection, metadata=metadata)

    def append_model_selection(
        self,
        selection: ModelSelectionSnapshot,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(MODEL_SELECTION_KIND, selection, metadata=metadata)

    def append_command_execution(
        self,
        command: CommandExecutionRecord,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(COMMAND_EXECUTION_KIND, command, metadata=metadata)

    def append_compaction_checkpoint(
        self,
        checkpoint: ContextCompactionCheckpoint,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(
            CONTEXT_COMPACTION_CHECKPOINT_KIND,
            checkpoint,
            metadata=metadata,
        )

    def append_branch_summary(
        self,
        summary: BranchContextSummary,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(CONTEXT_BRANCH_SUMMARY_KIND, summary, metadata=metadata)

    def append_application_message(
        self,
        message: ApplicationMessage,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(APPLICATION_MESSAGE_KIND, message, metadata=metadata)

    def append_extension_data(
        self,
        data: ExtensionData,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(EXTENSION_DATA_KIND, data, metadata=metadata)

    def append_annotation_patch(
        self,
        patch: RecordAnnotationPatch,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(RECORD_ANNOTATION_PATCH_KIND, patch, metadata=metadata)

    def append_metadata_patch(
        self,
        patch: ConversationMetadataPatch,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptRecord:
        return self.append(
            CONVERSATION_METADATA_PATCH_KIND,
            patch,
            metadata=metadata,
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid4())


def _encode_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise TypeError("transcript clock must return datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("transcript clock must return a timezone-aware datetime")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["AgentTranscriptWriter", "Clock", "IdFactory"]
