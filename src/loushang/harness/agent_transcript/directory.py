"""Reusable directory and index operations for current Agent transcripts.

Products choose a transcript root and when to request refreshes. This runtime
owns only current Native transcript discovery, query projection, index refresh,
and coalesced refresh scheduling; it does not create sessions or choose a
Product's lifecycle, model, extension, or diagnostics policy.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import monotonic

from loushang.harness.agent_transcript.catalog import (
    AgentTranscriptSessionCatalog,
    SessionQuery,
    SessionRecord,
    SessionSummary,
    find_all_agent_transcript_session_summaries,
    find_all_indexed_agent_transcript_session_summaries,
    list_all_agent_transcript_session_summaries,
    list_all_indexed_agent_transcript_session_summaries,
    refresh_all_agent_transcript_session_indexes,
)
from loushang.harness.runtime import CoalescingScheduler

IndexRefreshFailureRecorder = Callable[[Exception, bool], None]


class AgentTranscriptDirectoryRuntime:
    """Expose catalog reads and bounded index refresh scheduling.

    The runtime is intentionally independent from active-session lifecycle.
    Products can reuse it beside their own session factory and decide whether
    index refreshes are automatic, explicit, or disabled.
    """

    def __init__(
        self,
        *,
        session_dir: str | Path,
        auto_refresh_session_index: bool = False,
        session_index_refresh_interval: float = 0.5,
        session_index_flush_delay: float = 0.25,
        record_index_refresh_failure: IndexRefreshFailureRecorder | None = None,
    ) -> None:
        self.session_dir = Path(session_dir)
        self.auto_refresh_session_index = auto_refresh_session_index
        self.session_index_refresh_interval = session_index_refresh_interval
        self.session_index_flush_delay = session_index_flush_delay
        self._record_index_refresh_failure = record_index_refresh_failure
        self._last_session_index_refresh = 0.0
        self._session_index_flush = CoalescingScheduler[bool](
            self._flush_scheduled_session_index,
            merge=lambda left, right: left or right,
            delay_seconds=session_index_flush_delay,
        )

    @property
    def session_catalog(self) -> AgentTranscriptSessionCatalog:
        """Return the current-root catalog without caching Product state."""

        return AgentTranscriptSessionCatalog(self.session_dir)

    def list_sessions(self) -> list[SessionRecord]:
        return self.session_catalog.list_records()

    def list_session_summaries(self) -> list[SessionSummary]:
        return self.session_catalog.list_summaries()

    def find_session_summaries(
        self,
        query: SessionQuery | None = None,
    ) -> list[SessionSummary]:
        return self.session_catalog.find_summaries(query)

    def list_all_session_summaries(self) -> list[SessionSummary]:
        return list_all_agent_transcript_session_summaries(self.session_dir.parent)

    def find_all_session_summaries(
        self,
        query: SessionQuery | None = None,
    ) -> list[SessionSummary]:
        return find_all_agent_transcript_session_summaries(
            self.session_dir.parent,
            query,
        )

    def refresh_session_index(self) -> list[SessionSummary]:
        summaries = self.session_catalog.refresh_index()
        self._last_session_index_refresh = monotonic()
        return summaries

    def refresh_all_session_indexes(self) -> list[SessionSummary]:
        summaries = refresh_all_agent_transcript_session_indexes(
            self.session_dir.parent
        )
        self._last_session_index_refresh = monotonic()
        return summaries

    def list_indexed_session_summaries(
        self,
        *,
        refresh: bool = False,
    ) -> list[SessionSummary]:
        if self.auto_refresh_session_index and not refresh:
            self.request_session_index_refresh_if_due()
        return self.session_catalog.list_indexed_summaries(refresh=refresh)

    def find_indexed_session_summaries(
        self,
        query: SessionQuery | None = None,
    ) -> list[SessionSummary]:
        return self.session_catalog.find_indexed_summaries(query)

    def list_all_indexed_session_summaries(
        self,
        *,
        refresh: bool = False,
    ) -> list[SessionSummary]:
        if self.auto_refresh_session_index and not refresh:
            self.request_session_index_refresh_if_due(all_sessions=True)
        return list_all_indexed_agent_transcript_session_summaries(
            self.session_dir.parent,
            refresh=refresh,
        )

    def find_all_indexed_session_summaries(
        self,
        query: SessionQuery | None = None,
    ) -> list[SessionSummary]:
        return find_all_indexed_agent_transcript_session_summaries(
            self.session_dir.parent,
            query,
        )

    def request_session_index_refresh(self, *, all_sessions: bool = False) -> None:
        """Schedule one best-effort index refresh after Product state changes."""

        self._session_index_flush.delay_seconds = self.session_index_flush_delay
        self._session_index_flush.schedule(all_sessions)

    def request_session_index_refresh_if_due(
        self,
        *,
        all_sessions: bool = False,
    ) -> None:
        if monotonic() - self._last_session_index_refresh >= (
            self.session_index_refresh_interval
        ):
            self.request_session_index_refresh(all_sessions=all_sessions)

    async def drain_session_index_flush(self) -> None:
        """Finish a pending refresh for deterministic Product disposal/tests."""

        await self._session_index_flush.drain()

    def _flush_scheduled_session_index(self, all_sessions: bool) -> None:
        try:
            if all_sessions:
                self.refresh_all_session_indexes()
            else:
                self.refresh_session_index()
        except Exception as exc:
            if self._record_index_refresh_failure is not None:
                self._record_index_refresh_failure(exc, all_sessions)


__all__ = [
    "AgentTranscriptDirectoryRuntime",
    "IndexRefreshFailureRecorder",
]
