from __future__ import annotations

from datetime import UTC, datetime

import pytest

from loushang.harness.agent_transcript import (
    APPLICATION_MESSAGE_KIND,
    AgentTranscriptWriter,
    ApplicationMessage,
    ApplicationMessageIdentityConflictError,
    TranscriptCommitter,
)
from loushang.harness.conversation import (
    ConversationHeader,
    ConversationRepository,
)


def _repository():
    return ConversationRepository.create(
        header=ConversationHeader(
            conversation_id="conversation-1",
            version=1,
            created_at="2026-07-16T00:00:00Z",
        ),
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
    )


def _ids(*values: str):
    values_iter = iter(values)
    return lambda: next(values_iter)


def _message(content: str = "notice") -> ApplicationMessage:
    return ApplicationMessage(
        application_message_id="application-1",
        custom_type="notice",
        content=content,
        timestamp=1.0,
    )


def test_writer_reads_current_repository_leaf_for_every_append() -> None:
    repository = _repository()
    writer = AgentTranscriptWriter(
        repository,
        clock=lambda: datetime(2026, 7, 16, tzinfo=UTC),
        id_factory=_ids("root", "left", "right"),
    )

    root = writer.append_application_message(_message("root"))
    left = writer.append_application_message(
        ApplicationMessage(
            application_message_id="application-left",
            custom_type="notice",
            content="left",
            timestamp=2.0,
        )
    )
    repository.branch(root.record_id)
    right = writer.append_application_message(
        ApplicationMessage(
            application_message_id="application-right",
            custom_type="notice",
            content="right",
            timestamp=3.0,
        )
    )

    assert root.parent_id is None
    assert left.parent_id == "root"
    assert right.parent_id == "root"
    assert right.created_at == "2026-07-16T00:00:00Z"


def test_committer_is_idempotent_and_rejects_identity_conflicts() -> None:
    repository = _repository()
    writer = AgentTranscriptWriter(
        repository,
        clock=lambda: datetime(2026, 7, 16, tzinfo=UTC),
        id_factory=_ids("record-1"),
    )
    committer = TranscriptCommitter(writer)

    first = committer.commit_application_message(_message())
    duplicate = committer.commit_application_message(_message())

    assert first.disposition == "committed"
    assert duplicate.disposition == "already_committed"
    assert duplicate.record_id == first.record_id
    assert len(repository.records) == 1
    assert repository.records[0].kind == APPLICATION_MESSAGE_KIND

    with pytest.raises(
        ApplicationMessageIdentityConflictError,
        match="different payload",
    ):
        committer.commit_application_message(_message("changed"))
    assert len(repository.records) == 1


def test_failed_append_is_not_memoized_as_committed() -> None:
    repository = _repository()
    writer = AgentTranscriptWriter(
        repository,
        clock=lambda: datetime(2026, 7, 16, tzinfo=UTC),
        id_factory=_ids("same", "same", "recovered"),
    )
    writer.append_application_message(
        ApplicationMessage(
            application_message_id="existing",
            custom_type="notice",
            content="existing",
            timestamp=0.0,
        )
    )
    committer = TranscriptCommitter(writer)

    with pytest.raises(ValueError, match="Duplicate branch record id"):
        committer.commit_application_message(_message())

    recovered = committer.commit_application_message(_message())
    assert recovered.disposition == "committed"
    assert recovered.record_id == "recovered"


def test_writer_requires_timezone_aware_clock() -> None:
    writer = AgentTranscriptWriter(
        _repository(),
        clock=lambda: datetime(2026, 7, 16),
        id_factory=_ids("record-1"),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        writer.append_application_message(_message())
