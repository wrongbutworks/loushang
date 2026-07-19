from __future__ import annotations

import builtins
from pathlib import Path

from loushang.coding.capability_plan import (
    coding_capability_snapshot_metadata,
    resolve_coding_capability_profile,
    validate_coding_capability_snapshot,
)
from loushang.coding.runtime_profile import (
    CodingRuntimeSessionBinding,
    CodingRuntimeSessionContext,
    bind_coding_runtime,
    coding_runtime_snapshot_metadata,
    resolve_coding_runtime_profile,
    selected_store,
    selected_transcript_profile,
    validate_coding_runtime_snapshot,
)
from loushang.harness.agent_transcript import (
    AgentTranscriptContext,
    AgentTranscriptLifecycle,
    AgentTranscriptLifecycleContext,
    AgentTranscriptLifecycleSession,
    AgentTranscriptRecord,
    AgentTranscriptRuntimeBinding,
    AgentTranscriptSession,
    AgentTranscriptSessionFactory,
    delete_current_native_agent_transcript,
)
from loushang.harness.agent_transcript.catalog import (
    AgentTranscriptSessionCatalog,
    SessionMetadata,
    SessionQuery,
    SessionRecord,
    SessionSummary,
    SessionTreeNode,
    agent_transcript_header_parent_session,
    build_agent_transcript_session_context,
    build_agent_transcript_session_tree,
    find_all_agent_transcript_session_summaries,
    find_all_indexed_agent_transcript_session_summaries,
    list_all_agent_transcript_session_summaries,
    list_all_indexed_agent_transcript_session_summaries,
    load_agent_transcript_session_metadata,
    project_agent_transcript_session_summary,
    refresh_all_agent_transcript_session_indexes,
)
from loushang.harness.conversation import ConversationHeader
from loushang.harness.runtime import ResolvedRuntimeProfile
from loushang.protocol import JSONValue, require_json_value

# Compatibility import path; the implementation is Harness-owned.
build_session_context = build_agent_transcript_session_context


async def _bind_coding_agent_transcript_runtime(
    context: AgentTranscriptLifecycleContext,
    runtime_profile: ResolvedRuntimeProfile,
) -> AgentTranscriptRuntimeBinding[CodingRuntimeSessionBinding]:
    coding_context = CodingRuntimeSessionContext(
        session_dir=context.session_dir,
        header=context.header,
        persist=context.persist,
        session_file=context.session_file,
    )
    binding = await bind_coding_runtime(
        profile=runtime_profile,
        context=coding_context,
    )
    return AgentTranscriptRuntimeBinding(
        store=selected_store(binding),
        key=coding_context.conversation_key,
        profile=selected_transcript_profile(binding),
        product_binding=binding,
        dispose=binding.dispose,
    )


_LIFECYCLE = AgentTranscriptLifecycle(
    bind_runtime=_bind_coding_agent_transcript_runtime
)


def _coding_header_metadata(
    runtime_profile: ResolvedRuntimeProfile,
) -> dict[str, JSONValue]:
    capability_profile = resolve_coding_capability_profile()
    return {
        **coding_runtime_snapshot_metadata(runtime_profile),
        **coding_capability_snapshot_metadata(capability_profile),
    }


def _validate_coding_restored_header(
    header: ConversationHeader,
    runtime_profile: ResolvedRuntimeProfile,
    persist: bool,
) -> None:
    snapshot = validate_coding_runtime_snapshot(header)
    capability_snapshot = validate_coding_capability_snapshot(header)
    capability_profile = resolve_coding_capability_profile()
    if persist and snapshot is not None and snapshot != runtime_profile.snapshot():
        raise ValueError(
            "Coding cannot resume a session with an unsupported runtime profile"
        )
    if (
        persist
        and capability_snapshot is not None
        and capability_snapshot != capability_profile.snapshot()
    ):
        raise ValueError(
            "Coding cannot resume a session with an unsupported capability profile"
        )


_FACTORY = AgentTranscriptSessionFactory(
    lifecycle=_LIFECYCLE,
    resolve_binding_input=resolve_coding_runtime_profile,
    header_metadata=_coding_header_metadata,
    validate_restored_header=_validate_coding_restored_header,
    session_file_factory=_LIFECYCLE.default_native_session_file,
)


class SessionManager(AgentTranscriptSession):
    def __init__(
        self,
        *,
        lifecycle_session: AgentTranscriptLifecycleSession[CodingRuntimeSessionBinding],
    ) -> None:
        self._lifecycle_session = lifecycle_session
        self.session_dir = lifecycle_session.context.session_dir
        self.cwd = lifecycle_session.context.cwd
        self.persist = lifecycle_session.context.persist
        self._runtime_binding = lifecycle_session.product_binding
        self.session_file = lifecycle_session.context.session_file
        super().__init__(
            transcript=lifecycle_session.transcript,
            labels_by_target_id=lifecycle_session.labels_by_target_id,
            label_timestamps_by_target_id=(
                lifecycle_session.label_timestamps_by_target_id
            ),
        )

    @property
    def runtime_profile(self) -> ResolvedRuntimeProfile:
        return self._runtime_binding.profile

    def get_runtime_capability(self, slot: str) -> object | tuple[object, ...]:
        return self._runtime_binding.value(slot)

    async def dispose_runtime_profile(self) -> None:
        await self._lifecycle_session.dispose()

    @classmethod
    async def new(
        cls,
        session_dir: Path,
        cwd: str,
        persist: bool = True,
        parent_session: str | None = None,
        session_id: str | None = None,
    ) -> SessionManager:
        lifecycle_session = await _FACTORY.new(
            session_dir=session_dir,
            cwd=cwd,
            persist=persist,
            parent_session=parent_session,
            session_id=session_id,
        )
        return cls(lifecycle_session=lifecycle_session)

    @classmethod
    async def load(cls, session_file: Path, persist: bool = True) -> SessionManager:
        lifecycle_session = await _FACTORY.load(session_file, persist=persist)
        return cls(lifecycle_session=lifecycle_session)

    @classmethod
    async def open(
        cls,
        session_file: str | Path,
        session_dir: str | Path | None = None,
        cwd_override: str | Path | None = None,
        persist: bool = True,
    ) -> SessionManager:
        lifecycle_session = await _FACTORY.open(
            session_file,
            session_dir=session_dir,
            cwd_override=cwd_override,
            persist=persist,
        )
        return cls(lifecycle_session=lifecycle_session)

    @classmethod
    async def continue_recent(
        cls, session_dir: str | Path, cwd: str | Path, persist: bool = True
    ) -> SessionManager:
        lifecycle_session = await _FACTORY.continue_recent(
            session_dir=session_dir,
            cwd=cwd,
            persist=persist,
        )
        return cls(lifecycle_session=lifecycle_session)

    @classmethod
    async def in_memory(
        cls, cwd: str | Path = ".", session_id: str | None = None
    ) -> SessionManager:
        lifecycle_session = await _FACTORY.in_memory(
            cwd=cwd,
            session_id=session_id,
        )
        return cls(lifecycle_session=lifecycle_session)

    @classmethod
    async def fork_from(
        cls,
        source_file: str | Path,
        target_cwd: str | Path,
        session_dir: str | Path,
        persist: bool = True,
    ) -> SessionManager:
        lifecycle_session = await _FACTORY.fork_from(
            source_file,
            target_cwd=target_cwd,
            session_dir=session_dir,
            persist=persist,
        )
        return cls(lifecycle_session=lifecycle_session)

    def get_session_dir(self) -> Path:
        return self.session_dir

    def get_session_file(self) -> Path | None:
        return self.session_file

    def get_cwd(self) -> str:
        return self.cwd

    def is_persisted(self) -> bool:
        return self.persist and self.session_file is not None

    def load_metadata(self) -> SessionMetadata:
        return load_agent_transcript_session_metadata(self.header, self.entries)

    def get_session_record(self) -> SessionRecord:
        return SessionRecord(
            session_id=self.header.conversation_id,
            cwd=self.cwd,
            session_file=self.session_file,
            parent_session=agent_transcript_header_parent_session(self.header),
            leaf_id=self.leaf_id,
            metadata=self.load_metadata(),
        )

    def get_session_summary(self) -> SessionSummary:
        return project_agent_transcript_session_summary(
            self.header,
            self.entries,
            self.leaf_id,
            self.session_file,
        )

    def get_tree(self) -> list[SessionTreeNode[AgentTranscriptRecord]]:
        return build_agent_transcript_session_tree(
            self._transcript.tree(),
            labels_by_target_id=self.labels_by_target_id,
            label_timestamps_by_target_id=self.label_timestamps_by_target_id,
        )

    async def append_custom_entry(
        self, custom_type: str, data: object | None = None
    ) -> str:
        return await self.append_extension_data(
            custom_type,
            require_json_value(data, name="custom_entry.data"),
        )

    async def append_diagnostic_metadata(
        self,
        *,
        code: str,
        level: str,
        message: str | None = None,
        details: object | None = None,
    ) -> str:
        payload: dict[str, object] = {"code": code, "level": level}
        if message is not None:
            payload["message"] = message
        if details is not None:
            payload["details"] = details
        return await self.append_custom_entry("diagnostic", payload)

    async def append_session_info(self, name: str | None) -> str:
        return await self.append_conversation_name(name)

    async def fork(self, leaf_id: str) -> SessionManager:
        lifecycle_session = await _FACTORY.fork(
            self._lifecycle_session,
            leaf_id=leaf_id,
            binding_input=self.runtime_profile,
        )
        return SessionManager(lifecycle_session=lifecycle_session)

    async def create_branched_session(self, leaf_id: str) -> Path | None:
        return (await self.fork(leaf_id)).session_file

    def build_session_context(self) -> AgentTranscriptContext:
        return self._transcript.replay_context()

    @classmethod
    async def rename_session(
        cls, session_file: str | Path, name: str | None
    ) -> SessionSummary:
        manager = await cls.open(session_file, persist=True)
        await manager.append_session_info(name)
        summary = manager.get_session_summary()
        cls._refresh_index_if_present(Path(session_file).expanduser().parent)
        return summary

    @classmethod
    async def delete_session(
        cls,
        session_file: str | Path,
        *,
        current_session_file: str | Path | None = None,
    ) -> bool:
        target = Path(session_file).expanduser()
        deleted = await delete_current_native_agent_transcript(
            target,
            current_session_file=current_session_file,
        )
        if deleted:
            cls._refresh_index_if_present(target.parent)
        return deleted

    @classmethod
    def _refresh_index_if_present(cls, session_dir: Path) -> None:
        if cls.index_file(session_dir).exists():
            try:
                cls.refresh_index(session_dir)
            except Exception:
                # Index files are an auxiliary cache; rename/delete already persisted the primary change.
                return

    @classmethod
    def list(cls, session_dir: Path) -> builtins.list[SessionRecord]:
        return AgentTranscriptSessionCatalog(session_dir).list_records()

    @classmethod
    def list_summaries(cls, session_dir: Path) -> builtins.list[SessionSummary]:
        return AgentTranscriptSessionCatalog(session_dir).list_summaries()

    @classmethod
    def list_all_summaries(cls, sessions_root: Path) -> builtins.list[SessionSummary]:
        return list_all_agent_transcript_session_summaries(sessions_root)

    @classmethod
    async def load_summary(cls, session_file: Path) -> SessionSummary:
        return (await cls.load(session_file)).get_session_summary()

    @classmethod
    def find_sessions(
        cls, session_dir: Path, query: SessionQuery | None = None
    ) -> builtins.list[SessionSummary]:
        return AgentTranscriptSessionCatalog(session_dir).find_summaries(query)

    @classmethod
    def find_all_sessions(
        cls, sessions_root: Path, query: SessionQuery | None = None
    ) -> builtins.list[SessionSummary]:
        return find_all_agent_transcript_session_summaries(sessions_root, query)

    @classmethod
    def index_file(cls, session_dir: Path) -> Path:
        return AgentTranscriptSessionCatalog(session_dir).index_path

    @classmethod
    def refresh_index(cls, session_dir: Path) -> builtins.list[SessionSummary]:
        return AgentTranscriptSessionCatalog(session_dir).refresh_index()

    @classmethod
    def load_index(cls, session_dir: Path) -> builtins.list[SessionSummary]:
        return AgentTranscriptSessionCatalog(session_dir).load_index()

    @classmethod
    def list_indexed_summaries(
        cls, session_dir: Path, *, refresh: bool = False
    ) -> builtins.list[SessionSummary]:
        return AgentTranscriptSessionCatalog(session_dir).list_indexed_summaries(
            refresh=refresh
        )

    @classmethod
    def find_indexed_sessions(
        cls, session_dir: Path, query: SessionQuery | None = None
    ) -> builtins.list[SessionSummary]:
        return AgentTranscriptSessionCatalog(session_dir).find_indexed_summaries(query)

    @classmethod
    def refresh_all_indexes(cls, sessions_root: Path) -> builtins.list[SessionSummary]:
        return refresh_all_agent_transcript_session_indexes(sessions_root)

    @classmethod
    def list_all_indexed_summaries(
        cls, sessions_root: Path, *, refresh: bool = False
    ) -> builtins.list[SessionSummary]:
        return list_all_indexed_agent_transcript_session_summaries(
            sessions_root, refresh=refresh
        )

    @classmethod
    def find_all_indexed_sessions(
        cls, sessions_root: Path, query: SessionQuery | None = None
    ) -> builtins.list[SessionSummary]:
        return find_all_indexed_agent_transcript_session_summaries(sessions_root, query)
