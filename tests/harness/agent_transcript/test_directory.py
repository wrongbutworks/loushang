from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.ai.types import UserMessage
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    AgentTranscriptDirectoryRuntime,
    SessionQuery,
    SessionSummary,
    write_agent_transcript_file,
)
from loushang.harness.conversation import ConversationHeader, ConversationRecord


def _header(conversation_id: str, *, cwd: str) -> ConversationHeader:
    return ConversationHeader(
        conversation_id=conversation_id,
        version=1,
        created_at="2026-07-19T00:00:00Z",
        metadata={"cwd": cwd},
    )


def _record(
    record_id: str,
    text: str,
    *,
    timestamp: float,
) -> ConversationRecord[object]:
    return ConversationRecord(
        record_id=record_id,
        parent_id=None,
        kind=AGENT_MESSAGE_KIND,
        payload_version=1,
        created_at="2026-07-19T00:00:01Z",
        payload=UserMessage(role="user", content=text, timestamp=timestamp),
    )


def test_directory_runtime_exposes_current_and_all_root_catalog_queries(
    tmp_path: Path,
) -> None:
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    write_agent_transcript_file(
        project_a / "alpha.jsonl",
        _header("alpha", cwd="/workspace/a"),
        [_record("alpha-record", "first searchable message", timestamp=1.0)],
    )
    write_agent_transcript_file(
        project_b / "beta.jsonl",
        _header("beta", cwd="/workspace/b"),
        [_record("beta-record", "second searchable message", timestamp=2.0)],
    )

    runtime = AgentTranscriptDirectoryRuntime(session_dir=project_a)

    assert [record.session_id for record in runtime.list_sessions()] == ["alpha"]
    assert [
        summary.session_id
        for summary in runtime.find_session_summaries(SessionQuery(text="first"))
    ] == ["alpha"]
    assert [
        summary.session_id
        for summary in runtime.find_all_session_summaries(SessionQuery(text="second"))
    ] == ["beta"]
    assert [summary.session_id for summary in runtime.refresh_session_index()] == [
        "alpha"
    ]
    assert [
        summary.session_id for summary in runtime.list_indexed_session_summaries()
    ] == ["alpha"]


def test_directory_runtime_coalesces_requested_index_refreshes(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_agent_transcript_file(
        project_dir / "alpha.jsonl",
        _header("alpha", cwd="/workspace/a"),
        [_record("alpha-record", "indexed message", timestamp=1.0)],
    )
    runtime = AgentTranscriptDirectoryRuntime(
        session_dir=project_dir,
        auto_refresh_session_index=True,
        session_index_flush_delay=60.0,
    )

    async def scenario() -> None:
        runtime.request_session_index_refresh()
        runtime.request_session_index_refresh(all_sessions=True)
        await runtime.drain_session_index_flush()

    asyncio.run(scenario())

    assert runtime.session_catalog.index_path.exists()
    assert [
        summary.session_id for summary in runtime.list_all_indexed_session_summaries()
    ] == ["alpha"]


def test_directory_runtime_contains_scheduled_refresh_failures(tmp_path: Path) -> None:
    failures: list[tuple[str, bool]] = []

    class _BrokenDirectoryRuntime(AgentTranscriptDirectoryRuntime):
        def refresh_session_index(self) -> list[SessionSummary]:
            raise RuntimeError("index unavailable")

    runtime = _BrokenDirectoryRuntime(
        session_dir=tmp_path,
        session_index_flush_delay=60.0,
        record_index_refresh_failure=lambda exc, all_sessions: failures.append(
            (str(exc), all_sessions)
        ),
    )

    async def scenario() -> None:
        runtime.request_session_index_refresh()
        await runtime.drain_session_index_flush()

    asyncio.run(scenario())

    assert failures == [("index unavailable", False)]
