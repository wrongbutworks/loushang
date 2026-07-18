from __future__ import annotations

import builtins
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from loushang.coding.capability_profile import (
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
    AgentTranscriptProfile,
    AgentTranscriptRecord,
    AgentTranscriptSession,
    AgentTranscriptSessionStore,
)
from loushang.harness.agent_transcript.catalog import (
    AgentTranscriptSessionCatalog,
    SessionMetadata,
    SessionQuery,
    SessionRecord,
    SessionSummary,
    SessionTreeNode,
    agent_transcript_header_cwd,
    agent_transcript_header_parent_session,
    build_agent_transcript_label_indexes,
    build_agent_transcript_session_context,
    build_agent_transcript_session_tree,
    find_all_agent_transcript_session_summaries,
    find_all_indexed_agent_transcript_session_summaries,
    list_all_agent_transcript_session_summaries,
    list_all_indexed_agent_transcript_session_summaries,
    load_agent_transcript_session_metadata,
    project_agent_transcript_session_summary,
    refresh_all_agent_transcript_session_indexes,
    same_agent_transcript_session_path,
)
from loushang.harness.agent_transcript.file_store import (
    AgentTranscriptFileLayout,
    create_agent_transcript_file_store,
    load_current_agent_transcript_header,
)
from loushang.harness.agent_transcript.migration import NATIVE_CONVERSATION_VERSION
from loushang.harness.conversation import (
    ConversationHeader,
)
from loushang.harness.runtime import ResolvedRuntimeProfile
from loushang.harness.storage import (
    ConversationKey,
    ConversationStore,
    StoreNotFoundError,
)
from loushang.protocol import JSONValue, require_json_value

CURRENT_SESSION_VERSION = NATIVE_CONVERSATION_VERSION


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _generate_id() -> str:
    return uuid4().hex[:8]


def _new_header(
    *,
    conversation_id: str,
    cwd: str,
    parent_conversation_id: str | None = None,
    parent_session: str | None = None,
    runtime_profile_metadata: Mapping[str, JSONValue] | None = None,
    capability_profile_metadata: Mapping[str, JSONValue] | None = None,
) -> ConversationHeader:
    metadata: dict[str, JSONValue] = {"cwd": str(cwd)}
    if parent_session is not None:
        metadata["parentSession"] = parent_session
    if runtime_profile_metadata is not None:
        metadata.update(runtime_profile_metadata)
    if capability_profile_metadata is not None:
        metadata.update(capability_profile_metadata)
    return ConversationHeader(
        conversation_id=conversation_id,
        version=CURRENT_SESSION_VERSION,
        created_at=_now_iso(),
        parent_conversation_id=parent_conversation_id,
        metadata=metadata,
    )


def _resolve_session_id(session_id: str | None) -> str:
    if session_id is None:
        return _generate_id()
    if not isinstance(session_id, str):
        raise TypeError("session_id must be a string")
    if not session_id.strip():
        raise ValueError("session_id must not be blank")
    return session_id


# Compatibility import path; the implementation is Harness-owned.
build_session_context = build_agent_transcript_session_context


async def _new_session_backend(
    *,
    session_dir: Path,
    header: ConversationHeader,
    persist: bool,
    session_file: Path | None = None,
    runtime_profile: ResolvedRuntimeProfile | None = None,
) -> tuple[
    CodingRuntimeSessionBinding,
    ConversationStore[ConversationHeader, AgentTranscriptRecord],
    ConversationKey,
    Path | None,
    AgentTranscriptProfile,
]:
    if persist and session_file is None:
        file_timestamp = header.created_at.replace(":", "-").replace(".", "-")
        session_file = session_dir / f"{file_timestamp}_{header.conversation_id}.jsonl"
    profile = runtime_profile or resolve_coding_runtime_profile(persist=persist)
    context = CodingRuntimeSessionContext(
        session_dir=session_dir,
        header=header,
        persist=persist,
        session_file=session_file,
    )
    binding = await bind_coding_runtime(profile=profile, context=context)
    return (
        binding,
        selected_store(binding),
        context.conversation_key,
        session_file,
        selected_transcript_profile(binding),
    )


class SessionManager(AgentTranscriptSession):
    def __init__(
        self,
        *,
        session_dir: Path,
        cwd: str,
        persist: bool,
        transcript: AgentTranscriptSessionStore,
        runtime_binding: CodingRuntimeSessionBinding,
        session_file: Path | None = None,
        labels_by_target_id: dict[str, str] | None = None,
        label_timestamps_by_target_id: dict[str, str] | None = None,
    ) -> None:
        self.session_dir = session_dir
        self.cwd = cwd
        self.persist = persist
        self._runtime_binding = runtime_binding
        self.session_file = session_file
        super().__init__(
            transcript=transcript,
            labels_by_target_id=labels_by_target_id,
            label_timestamps_by_target_id=label_timestamps_by_target_id,
            application_message_id_factory=_generate_id,
        )

    @property
    def runtime_profile(self) -> ResolvedRuntimeProfile:
        return self._runtime_binding.profile

    def get_runtime_capability(self, slot: str) -> object | tuple[object, ...]:
        return self._runtime_binding.value(slot)

    async def dispose_runtime_profile(self) -> None:
        await self._runtime_binding.dispose()

    @classmethod
    async def new(
        cls,
        session_dir: Path,
        cwd: str,
        persist: bool = True,
        parent_session: str | None = None,
        session_id: str | None = None,
    ) -> SessionManager:
        resolved_session_id = _resolve_session_id(session_id)
        normalized_cwd = str(cwd)
        runtime_profile = resolve_coding_runtime_profile(persist=persist)
        capability_profile = resolve_coding_capability_profile()
        header = _new_header(
            conversation_id=resolved_session_id,
            cwd=normalized_cwd,
            parent_session=parent_session,
            runtime_profile_metadata=coding_runtime_snapshot_metadata(runtime_profile),
            capability_profile_metadata=coding_capability_snapshot_metadata(
                capability_profile
            ),
        )
        (
            runtime_binding,
            backend,
            key,
            session_file,
            transcript_profile,
        ) = await _new_session_backend(
            session_dir=Path(session_dir),
            header=header,
            persist=persist,
            runtime_profile=runtime_profile,
        )
        try:
            transcript = await AgentTranscriptSessionStore.create(
                backend,
                key,
                header,
                id_factory=_generate_id,
                profile=transcript_profile,
            )
        except Exception:
            await runtime_binding.dispose()
            raise
        return cls(
            session_dir=Path(session_dir),
            cwd=normalized_cwd,
            persist=persist,
            transcript=transcript,
            runtime_binding=runtime_binding,
            session_file=session_file,
        )

    @classmethod
    async def load(cls, session_file: Path, persist: bool = True) -> SessionManager:
        path = Path(session_file).expanduser().resolve(strict=False)
        header = load_current_agent_transcript_header(path)
        snapshot = validate_coding_runtime_snapshot(header)
        capability_snapshot = validate_coding_capability_snapshot(header)
        runtime_profile = resolve_coding_runtime_profile(persist=persist)
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
        (
            runtime_binding,
            backend,
            key,
            _,
            transcript_profile,
        ) = await _new_session_backend(
            session_dir=path.parent,
            header=header,
            persist=persist,
            session_file=path,
            runtime_profile=runtime_profile,
        )
        try:
            if persist:
                transcript = await AgentTranscriptSessionStore.load(
                    backend,
                    key,
                    id_factory=_generate_id,
                    profile=transcript_profile,
                )
            else:
                layout = AgentTranscriptFileLayout(path.parent)
                layout.bind_existing_path(path)
                source_backend = create_agent_transcript_file_store(layout)
                source_key = layout.key(header.conversation_id)
                source_snapshot = await source_backend.load(source_key)
                transcript = await AgentTranscriptSessionStore.create(
                    backend,
                    key,
                    source_snapshot.header,
                    records=source_snapshot.records,
                    id_factory=_generate_id,
                    profile=transcript_profile,
                )
        except Exception:
            await runtime_binding.dispose()
            raise
        header = transcript.header
        entries = list(transcript.records)
        labels_by_target_id, label_timestamps_by_target_id = (
            build_agent_transcript_label_indexes(entries)
        )
        return cls(
            session_dir=path.parent,
            cwd=agent_transcript_header_cwd(header),
            persist=persist,
            transcript=transcript,
            runtime_binding=runtime_binding,
            session_file=path,
            labels_by_target_id=labels_by_target_id,
            label_timestamps_by_target_id=label_timestamps_by_target_id,
        )

    @classmethod
    async def open(
        cls,
        session_file: str | Path,
        session_dir: str | Path | None = None,
        cwd_override: str | Path | None = None,
        persist: bool = True,
    ) -> SessionManager:
        path = Path(session_file)
        manager = await cls.load(path, persist=persist)
        if session_dir is not None:
            manager.session_dir = Path(session_dir)
        if cwd_override is not None:
            cwd = str(cwd_override)
            manager.cwd = cwd
        return manager

    @classmethod
    async def continue_recent(
        cls, session_dir: str | Path, cwd: str | Path, persist: bool = True
    ) -> SessionManager:
        summaries = cls.list_summaries(Path(session_dir))
        for summary in summaries:
            if summary.session_file is None:
                continue
            return await cls.open(
                summary.session_file,
                session_dir=session_dir,
                cwd_override=cwd,
                persist=persist,
            )
        return await cls.new(
            session_dir=Path(session_dir), cwd=str(cwd), persist=persist
        )

    @classmethod
    async def in_memory(
        cls, cwd: str | Path = ".", session_id: str | None = None
    ) -> SessionManager:
        return await cls.new(
            session_dir=Path(), cwd=str(cwd), persist=False, session_id=session_id
        )

    @classmethod
    async def fork_from(
        cls,
        source_file: str | Path,
        target_cwd: str | Path,
        session_dir: str | Path,
        persist: bool = True,
    ) -> SessionManager:
        source = await cls.load(Path(source_file), persist=False)
        source_header = source.header
        source_entries = source.get_entries()
        await source.dispose_runtime_profile()
        runtime_profile = resolve_coding_runtime_profile(persist=persist)
        capability_profile = resolve_coding_capability_profile()
        header = _new_header(
            conversation_id=_generate_id(),
            cwd=str(target_cwd),
            parent_conversation_id=source_header.conversation_id,
            parent_session=str(Path(source_file)),
            runtime_profile_metadata=coding_runtime_snapshot_metadata(runtime_profile),
            capability_profile_metadata=coding_capability_snapshot_metadata(
                capability_profile
            ),
        )
        target_dir = Path(session_dir)
        (
            runtime_binding,
            backend,
            key,
            session_file,
            transcript_profile,
        ) = await _new_session_backend(
            session_dir=target_dir,
            header=header,
            persist=persist,
            runtime_profile=runtime_profile,
        )
        try:
            transcript = await AgentTranscriptSessionStore.create(
                backend,
                key,
                header,
                records=source_entries,
                id_factory=_generate_id,
                profile=transcript_profile,
            )
        except Exception:
            await runtime_binding.dispose()
            raise
        labels_by_target_id, label_timestamps_by_target_id = (
            build_agent_transcript_label_indexes(source_entries)
        )
        return cls(
            session_dir=target_dir,
            cwd=str(target_cwd),
            persist=persist,
            transcript=transcript,
            runtime_binding=runtime_binding,
            session_file=session_file,
            labels_by_target_id=labels_by_target_id,
            label_timestamps_by_target_id=label_timestamps_by_target_id,
        )

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
        branch_entries = self.get_branch(leaf_id)
        labels_by_target_id, label_timestamps_by_target_id = (
            build_agent_transcript_label_indexes(branch_entries)
        )
        parent_session = (
            str(self.session_file) if self.session_file is not None else None
        )
        header = _new_header(
            conversation_id=_generate_id(),
            cwd=self.cwd,
            parent_conversation_id=self.header.conversation_id,
            parent_session=parent_session,
            runtime_profile_metadata=coding_runtime_snapshot_metadata(
                self.runtime_profile
            ),
            capability_profile_metadata=coding_capability_snapshot_metadata(
                resolve_coding_capability_profile()
            ),
        )

        (
            runtime_binding,
            backend,
            key,
            session_file,
            transcript_profile,
        ) = await _new_session_backend(
            session_dir=self.session_dir,
            header=header,
            persist=self.persist,
            runtime_profile=self.runtime_profile,
        )
        try:
            transcript = await AgentTranscriptSessionStore.create(
                backend,
                key,
                header,
                records=branch_entries,
                leaf_id=leaf_id,
                id_factory=_generate_id,
                profile=transcript_profile,
            )
        except Exception:
            await runtime_binding.dispose()
            raise

        return SessionManager(
            session_dir=self.session_dir,
            cwd=self.cwd,
            persist=self.persist,
            transcript=transcript,
            runtime_binding=runtime_binding,
            session_file=session_file,
            labels_by_target_id=labels_by_target_id,
            label_timestamps_by_target_id=label_timestamps_by_target_id,
        )

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
        if current_session_file is not None and same_agent_transcript_session_path(
            target, Path(current_session_file).expanduser()
        ):
            raise ValueError("Cannot delete the currently active session")
        if not target.is_file():
            return False
        layout = AgentTranscriptFileLayout(target.parent)
        key = layout.bind_existing_path(target)
        try:
            await create_agent_transcript_file_store(layout).delete(key)
        except StoreNotFoundError:
            return False
        cls._refresh_index_if_present(target.parent)
        return True

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
