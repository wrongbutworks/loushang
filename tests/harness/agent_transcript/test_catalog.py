from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.ai.types import UserMessage
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    RECORD_ANNOTATION_PATCH_KIND,
    AgentTranscriptSessionCatalog,
    RecordAnnotationPatch,
    SessionQuery,
    build_agent_transcript_label_indexes,
    build_agent_transcript_session_context,
    find_all_agent_transcript_session_summaries,
    project_session_record,
    write_agent_transcript_export,
)
from loushang.harness.conversation import (
    ConversationHeader,
    ConversationKey,
    ConversationProviderBinding,
    ConversationRecord,
    MemoryConversationStore,
)


def _header(conversation_id: str, *, cwd: str) -> ConversationHeader:
    return ConversationHeader(
        conversation_id=conversation_id,
        version=1,
        created_at="2026-07-18T00:00:00Z",
        metadata={"cwd": cwd},
    )


def _record(
    record_id: str,
    text: str,
    *,
    parent_id: str | None = None,
    timestamp: float = 1.0,
) -> ConversationRecord[object]:
    return ConversationRecord(
        record_id=record_id,
        parent_id=parent_id,
        kind=AGENT_MESSAGE_KIND,
        payload_version=1,
        created_at="2026-07-18T00:00:01Z",
        payload=UserMessage(role="user", content=text, timestamp=timestamp),
    )


def test_catalog_discovers_queries_and_indexes_current_native_transcripts(
    tmp_path: Path,
) -> None:
    write_agent_transcript_export(
        tmp_path / "alpha.jsonl",
        _header("alpha", cwd="/workspace/a"),
        [_record("alpha-record", "first searchable message")],
    )
    write_agent_transcript_export(
        tmp_path / "beta.jsonl",
        _header("beta", cwd="/workspace/b"),
        [_record("beta-record", "another message", timestamp=2.0)],
    )

    catalog = AgentTranscriptSessionCatalog(tmp_path)

    assert [record.session_id for record in catalog.list_records()] == ["beta", "alpha"]
    assert [
        summary.session_id
        for summary in catalog.find_summaries(SessionQuery(text="searchable"))
    ] == ["alpha"]
    assert [summary.session_id for summary in catalog.refresh_index()] == [
        "beta",
        "alpha",
    ]
    assert [summary.session_id for summary in catalog.list_indexed_summaries()] == [
        "beta",
        "alpha",
    ]
    assert [
        summary.session_id
        for summary in find_all_agent_transcript_session_summaries(
            tmp_path, SessionQuery(cwd="/workspace/b")
        )
    ] == ["beta"]


def test_catalog_context_and_labels_use_selected_standard_record_path() -> None:
    root = _record("root", "root")
    selected = _record("selected", "selected branch", parent_id="root")
    other = _record("other", "other branch", parent_id="root")
    label = ConversationRecord(
        record_id="label",
        parent_id="selected",
        kind=RECORD_ANNOTATION_PATCH_KIND,
        payload_version=1,
        created_at="2026-07-18T00:00:02Z",
        payload=RecordAnnotationPatch(
            target_record_id="selected",
            namespace="display.label",
            operation="set",
            value="important",
        ),
    )

    context = build_agent_transcript_session_context(
        [root, selected, other, label], leaf_id="selected"
    )
    labels, timestamps = build_agent_transcript_label_indexes(
        [root, selected, other, label]
    )

    assert [message.content for message in context.messages] == [
        "root",
        "selected branch",
    ]
    assert labels == {"selected": "important"}
    assert timestamps == {"selected": "2026-07-18T00:00:02Z"}


def test_agent_catalog_projects_a_non_file_store_provider() -> None:
    namespace = "remote"
    key = ConversationKey(namespace, "remote-session")
    store = MemoryConversationStore(record_id=lambda record: record.record_id)

    async def create() -> None:
        await store.create(
            key,
            _header("remote-session", cwd="/workspace/remote"),
            [_record("remote-record", "remote message")],
            operation_id="create:remote-session",
        )

    asyncio.run(create())
    catalog = AgentTranscriptSessionCatalog.from_provider(
        ConversationProviderBinding("remote-provider", namespace, store)
    )

    summaries = catalog.list_summaries()

    assert [summary.session_id for summary in summaries] == ["remote-session"]
    assert summaries[0].session_file is None
    assert summaries[0].locator is not None
    assert summaries[0].locator.provider_id == "remote-provider"


def test_project_session_record_preserves_catalog_listing_shape() -> None:
    record = SessionRecordLike(
        session_id="session-1",
        cwd="/workspace",
        session_file=Path("/tmp/session.jsonl"),
        parent_session=None,
        leaf_id="leaf-1",
        metadata=MetadataLike(
            created_at="2026-07-18T00:00:00Z",
            updated_at="2026-07-18T00:00:01Z",
            name="Demo",
        ),
        message_count=2,
        model={"provider": "test", "model_id": "small"},
    )

    assert project_session_record(record) == {
        "session_id": "session-1",
        "cwd": "/workspace",
        "session_file": "/tmp/session.jsonl",
        "parent_session": None,
        "leaf_id": "leaf-1",
        "metadata": {
            "created_at": "2026-07-18T00:00:00Z",
            "updated_at": "2026-07-18T00:00:01Z",
            "name": "Demo",
        },
        "message_count": 2,
        "model": {"provider": "test", "model_id": "small"},
    }


class MetadataLike:
    def __init__(self, *, created_at: str, updated_at: str, name: str) -> None:
        self.created_at = created_at
        self.updated_at = updated_at
        self.name = name


class SessionRecordLike:
    def __init__(
        self,
        *,
        session_id: str,
        cwd: str,
        session_file: Path,
        parent_session: str | None,
        leaf_id: str | None,
        metadata: MetadataLike,
        message_count: int,
        model: dict[str, str],
    ) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.session_file = session_file
        self.parent_session = parent_session
        self.leaf_id = leaf_id
        self.metadata = metadata
        self.message_count = message_count
        self.model = model
