from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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
from loushang.harness.agent_transcript.profile import AgentTranscriptProfile
from loushang.harness.agent_transcript.types import (
    AgentTranscriptContext,
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
from loushang.harness.agent_transcript.writer import (
    AgentTranscriptRecordFactory,
    Clock,
    IdFactory,
)
from loushang.harness.conversation.repository import ConversationRepository
from loushang.harness.conversation.types import (
    BranchDelta,
    CommandExecutionRecord,
    ConversationHeader,
    ConversationTreeNode,
)
from loushang.harness.storage import CommitReceipt, ConversationKey, ConversationStore
from loushang.protocol import JSONValue


@dataclass(frozen=True)
class AgentTranscriptCommit:
    """One record paired with the backend receipt that durably committed it."""

    record: AgentTranscriptRecord
    receipt: CommitReceipt


class AgentTranscriptSessionStore:
    """One durable Agent transcript stream and its journal-free runtime view."""

    def __init__(
        self,
        *,
        backend: ConversationStore[ConversationHeader, AgentTranscriptRecord],
        key: ConversationKey,
        repository: ConversationRepository[
            ConversationHeader,
            AgentTranscriptRecord,
        ],
        revision: int,
        record_factory: AgentTranscriptRecordFactory | None = None,
        profile: AgentTranscriptProfile | None = None,
    ) -> None:
        if revision != len(repository.records):
            raise ValueError("transcript store revision must equal its record count")
        if repository.header.conversation_id != key.conversation_id:
            raise ValueError("conversation key and header id must match")
        self._backend = backend
        self._key = key
        self._repository = repository
        self._revision = revision
        self._record_factory = record_factory or AgentTranscriptRecordFactory()
        self._profile = profile or AgentTranscriptProfile.default()
        self._commit_lock = asyncio.Lock()

    @classmethod
    async def create(
        cls,
        backend: ConversationStore[ConversationHeader, AgentTranscriptRecord],
        key: ConversationKey,
        header: ConversationHeader,
        *,
        records: Sequence[AgentTranscriptRecord] = (),
        leaf_id: str | None = None,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
        record_factory: AgentTranscriptRecordFactory | None = None,
        profile: AgentTranscriptProfile | None = None,
    ) -> AgentTranscriptSessionStore:
        _require_matching_identity(key, header)
        initial_records = tuple(records)
        _create_repository(
            header=header,
            records=initial_records,
            leaf_id=leaf_id,
        )
        snapshot = await backend.create(key, header, initial_records)
        repository = _create_repository(
            header=snapshot.header,
            records=snapshot.records,
            leaf_id=leaf_id,
        )
        return cls(
            backend=backend,
            key=key,
            repository=repository,
            revision=snapshot.revision,
            record_factory=record_factory
            or AgentTranscriptRecordFactory(clock=clock, id_factory=id_factory),
            profile=profile,
        )

    @classmethod
    async def load(
        cls,
        backend: ConversationStore[ConversationHeader, AgentTranscriptRecord],
        key: ConversationKey,
        *,
        leaf_id: str | None = None,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
        record_factory: AgentTranscriptRecordFactory | None = None,
        profile: AgentTranscriptProfile | None = None,
    ) -> AgentTranscriptSessionStore:
        snapshot = await backend.load(key)
        _require_matching_identity(key, snapshot.header)
        repository = _create_repository(
            header=snapshot.header,
            records=snapshot.records,
            leaf_id=leaf_id,
        )
        return cls(
            backend=backend,
            key=key,
            repository=repository,
            revision=snapshot.revision,
            record_factory=record_factory
            or AgentTranscriptRecordFactory(clock=clock, id_factory=id_factory),
            profile=profile,
        )

    @property
    def backend(
        self,
    ) -> ConversationStore[ConversationHeader, AgentTranscriptRecord]:
        return self._backend

    @property
    def key(self) -> ConversationKey:
        return self._key

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def header(self) -> ConversationHeader:
        return self._repository.header

    @property
    def records(self) -> tuple[AgentTranscriptRecord, ...]:
        return self._repository.records

    @property
    def leaf_id(self) -> str | None:
        return self._repository.leaf_id

    def get(self, record_id: str) -> AgentTranscriptRecord | None:
        return self._repository.get(record_id)

    def leaf(self) -> AgentTranscriptRecord | None:
        return self._repository.leaf()

    def children(self, record_id: str) -> tuple[AgentTranscriptRecord, ...]:
        return self._repository.children(record_id)

    def branch(self, record_id: str) -> None:
        self._require_idle_commit("select a transcript branch")
        self._repository.branch(record_id)

    def reset_branch(self) -> None:
        self._require_idle_commit("reset the transcript branch")
        self._repository.reset_branch()

    def tree(self) -> tuple[ConversationTreeNode[AgentTranscriptRecord], ...]:
        return self._repository.tree()

    def active_path(self) -> tuple[AgentTranscriptRecord, ...]:
        return self._repository.active_records()

    def records_to(self, record_id: str) -> tuple[AgentTranscriptRecord, ...]:
        return self._repository.records_to(record_id)

    def branch_delta(
        self,
        from_id: str,
        target_id: str,
    ) -> BranchDelta[AgentTranscriptRecord]:
        return self._repository.branch_delta(from_id, target_id)

    def replay_context(self) -> AgentTranscriptContext:
        return self._profile.replay(self.active_path())

    async def commit(self, record: AgentTranscriptRecord) -> AgentTranscriptCommit:
        """Durably append one prebuilt record, then advance runtime state."""

        async with self._commit_lock:
            return await self._commit_locked(record)

    async def append(
        self,
        kind: str,
        payload: AgentTranscriptPayload,
        *,
        payload_version: int = STANDARD_PAYLOAD_VERSION,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        async with self._commit_lock:
            record = self._record_factory.create(
                kind,
                payload,
                parent_id=self.leaf_id,
                payload_version=payload_version,
                metadata=metadata,
            )
            return await self._commit_locked(record)

    async def append_agent_message(
        self,
        message: Message,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(AGENT_MESSAGE_KIND, message, metadata=metadata)

    async def append_thinking_selection(
        self,
        selection: ThinkingSelectionSnapshot,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(THINKING_SELECTION_KIND, selection, metadata=metadata)

    async def append_model_selection(
        self,
        selection: ModelSelectionSnapshot,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(MODEL_SELECTION_KIND, selection, metadata=metadata)

    async def append_command_execution(
        self,
        command: CommandExecutionRecord,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(COMMAND_EXECUTION_KIND, command, metadata=metadata)

    async def append_compaction_checkpoint(
        self,
        checkpoint: ContextCompactionCheckpoint,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(
            CONTEXT_COMPACTION_CHECKPOINT_KIND,
            checkpoint,
            metadata=metadata,
        )

    async def append_branch_summary(
        self,
        summary: BranchContextSummary,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(
            CONTEXT_BRANCH_SUMMARY_KIND, summary, metadata=metadata
        )

    async def append_application_message(
        self,
        message: ApplicationMessage,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(APPLICATION_MESSAGE_KIND, message, metadata=metadata)

    async def append_extension_data(
        self,
        data: ExtensionData,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(EXTENSION_DATA_KIND, data, metadata=metadata)

    async def append_annotation_patch(
        self,
        patch: RecordAnnotationPatch,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(RECORD_ANNOTATION_PATCH_KIND, patch, metadata=metadata)

    async def append_metadata_patch(
        self,
        patch: ConversationMetadataPatch,
        *,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> AgentTranscriptCommit:
        return await self.append(
            CONVERSATION_METADATA_PATCH_KIND,
            patch,
            metadata=metadata,
        )

    async def fork(
        self,
        target_key: ConversationKey,
        header: ConversationHeader,
        *,
        leaf_id: str | None = None,
    ) -> AgentTranscriptSessionStore:
        async with self._commit_lock:
            selected_id = self.leaf_id if leaf_id is None else leaf_id
            records = self.records_to(selected_id) if selected_id is not None else ()
            return await type(self).create(
                self._backend,
                target_key,
                header,
                records=records,
                leaf_id=records[-1].record_id if records else None,
                record_factory=self._record_factory,
                profile=self._profile,
            )

    async def _commit_locked(
        self,
        record: AgentTranscriptRecord,
    ) -> AgentTranscriptCommit:
        if record.parent_id != self.leaf_id:
            raise ValueError(
                "transcript record parent must match the selected leaf: "
                f"expected {self.leaf_id!r}, got {record.parent_id!r}"
            )
        candidate = _create_repository(
            header=self.header,
            records=(*self.records, record),
            leaf_id=record.record_id,
        )
        receipt = await self._backend.append(
            self._key,
            record,
            expected_revision=self._revision,
        )
        expected_revision = self._revision + 1
        if receipt.revision != expected_revision:
            raise RuntimeError(
                "conversation backend returned an invalid append revision: "
                f"expected {expected_revision}, got {receipt.revision}"
            )
        if receipt.record_id not in {None, record.record_id}:
            raise RuntimeError(
                "conversation backend returned a different committed record id"
            )
        self._repository = candidate
        self._revision = receipt.revision
        return AgentTranscriptCommit(record=record, receipt=receipt)

    def _require_idle_commit(self, operation: str) -> None:
        if self._commit_lock.locked():
            raise RuntimeError(f"cannot {operation} while a commit is in progress")


def _create_repository(
    *,
    header: ConversationHeader,
    records: Sequence[AgentTranscriptRecord],
    leaf_id: str | None,
) -> ConversationRepository[ConversationHeader, AgentTranscriptRecord]:
    return ConversationRepository.create(
        header=header,
        records=records,
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        leaf_id=leaf_id,
    )


def _require_matching_identity(
    key: ConversationKey,
    header: ConversationHeader,
) -> None:
    if header.conversation_id != key.conversation_id:
        raise ValueError("conversation key and header id must match")


__all__ = ["AgentTranscriptCommit", "AgentTranscriptSessionStore"]
