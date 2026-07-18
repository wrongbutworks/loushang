from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from loushang.agent import AgentMessage
from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, UserMessage
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
from loushang.coding.store.types import (
    SessionMetadata,
    SessionQuery,
    SessionRecord,
    SessionSummary,
    SessionTreeNode,
)
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    EXTENSION_DATA_KIND,
    RECORD_ANNOTATION_PATCH_KIND,
    AgentTranscriptContext,
    AgentTranscriptProfile,
    AgentTranscriptRecord,
    AgentTranscriptSession,
    AgentTranscriptSessionStore,
    ApplicationMessage,
    ExtensionData,
    RecordAnnotationPatch,
)
from loushang.harness.agent_transcript.file_store import (
    AgentTranscriptFileLayout,
    create_agent_transcript_file_store,
    load_agent_transcript_repository,
    load_current_agent_transcript_header,
)
from loushang.harness.agent_transcript.migration import NATIVE_CONVERSATION_VERSION
from loushang.harness.conversation import (
    ConversationCatalog,
    ConversationHeader,
    ConversationRepository,
    ConversationTreeNode,
    FunctionalConversationProjector,
    ProjectionQuery,
)
from loushang.harness.journal import (
    FunctionalProjectionCodec,
    JsonProjectionIndex,
    ProjectionIndexSnapshot,
)
from loushang.harness.runtime import ResolvedRuntimeProfile
from loushang.harness.storage import (
    ConversationKey,
    ConversationStore,
    StoreNotFoundError,
)
from loushang.observability import get_log
from loushang.protocol import require_json_value

CURRENT_SESSION_VERSION = NATIVE_CONVERSATION_VERSION
_LEAF_UNSET = object()
_SESSION_INDEX_VERSION = 1
_SESSION_INDEX_FILENAME = ".session-index.json"
log = get_log(__name__).bind(component="SessionManager")


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
    runtime_profile_metadata: dict[str, object] | None = None,
    capability_profile_metadata: dict[str, object] | None = None,
) -> ConversationHeader:
    metadata: dict[str, object] = {"cwd": str(cwd)}
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


def _header_cwd(header: ConversationHeader) -> str:
    cwd = header.metadata.get("cwd")
    return cwd if isinstance(cwd, str) else ""


def _header_parent_session(header: ConversationHeader) -> str | None:
    parent = header.metadata.get("parentSession")
    return parent if isinstance(parent, str) else None


def _resolve_session_id(session_id: str | None) -> str:
    if session_id is None:
        return _generate_id()
    if not isinstance(session_id, str):
        raise TypeError("session_id must be a string")
    if not session_id.strip():
        raise ValueError("session_id must not be blank")
    return session_id


def _normalize_label(label: str | None) -> str | None:
    if not isinstance(label, str):
        return None
    normalized = label.strip()
    return normalized or None


def _normalize_session_name(name: str | None) -> str | None:
    if not isinstance(name, str):
        return None
    normalized = name.strip()
    return normalized or None


def _build_label_indexes(
    entries: list[AgentTranscriptRecord],
) -> tuple[dict[str, str], dict[str, str]]:
    labels_by_target_id: dict[str, str] = {}
    label_timestamps_by_target_id: dict[str, str] = {}
    for entry in entries:
        patch = entry.payload
        if entry.kind != RECORD_ANNOTATION_PATCH_KIND or not isinstance(
            patch, RecordAnnotationPatch
        ):
            continue
        if patch.namespace != "display.label":
            continue
        if patch.operation == "set" and isinstance(patch.value, str):
            labels_by_target_id[patch.target_record_id] = patch.value
            label_timestamps_by_target_id[patch.target_record_id] = entry.created_at
        else:
            labels_by_target_id.pop(patch.target_record_id, None)
            label_timestamps_by_target_id.pop(patch.target_record_id, None)
    return labels_by_target_id, label_timestamps_by_target_id


_AGENT_TRANSCRIPT_PROFILE = AgentTranscriptProfile.default()


def _replay_session(
    entries: Sequence[AgentTranscriptRecord],
) -> AgentTranscriptContext:
    return _AGENT_TRANSCRIPT_PROFILE.replay(entries)


def _message_preview(message: AgentMessage) -> str | None:
    if isinstance(message, UserMessage | AssistantMessage | ToolResultMessage):
        parts = getattr(message, "content", None)
        if isinstance(parts, str):
            text = parts
        elif isinstance(parts, list):
            text = " ".join(part.text for part in parts if isinstance(part, TextPart))
        else:
            text = ""
        normalized = " ".join(text.split())
        return normalized[:160] if normalized else None
    if isinstance(message, ApplicationMessage):
        content = message.content
        if isinstance(content, str):
            return " ".join(content.split())[:160] or None
    return None


def _message_text(message: AgentMessage) -> str | None:
    if isinstance(message, UserMessage | AssistantMessage):
        parts = getattr(message, "content", None)
        if isinstance(parts, str):
            text = parts
        elif isinstance(parts, list):
            text = " ".join(part.text for part in parts if isinstance(part, TextPart))
        else:
            text = ""
        normalized = " ".join(text.split())
        return normalized or None
    return None


def _iso_from_unix_seconds(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _normalize_unix_timestamp_seconds(timestamp: float) -> float:
    # Agent messages use millisecond timestamps, while older tests and entries may
    # still carry second timestamps. Anything past year 3000 in seconds is treated
    # as milliseconds for metadata indexing.
    if timestamp > 32_503_680_000:
        normalized = timestamp / 1000
        log.problem(
            "session_timestamp_normalized",
            severity="warning",
            source="session",
            message="Session message timestamp looked like milliseconds and was normalized to seconds.",
            recoverable=True,
            original_timestamp=timestamp,
            normalized_timestamp=normalized,
            unit="milliseconds",
        )
        return normalized
    return timestamp


def _last_activity_timestamp(
    entries: list[AgentTranscriptRecord], header: ConversationHeader
) -> str:
    last_message_timestamp: float | None = None
    last_entry_timestamp: str | None = None
    for entry in entries:
        if entry.kind != AGENT_MESSAGE_KIND:
            continue
        message = entry.payload
        if not isinstance(message, UserMessage | AssistantMessage):
            continue
        timestamp = getattr(message, "timestamp", None)
        if isinstance(timestamp, int | float) and timestamp > 0:
            last_message_timestamp = max(
                last_message_timestamp or 0,
                _normalize_unix_timestamp_seconds(float(timestamp)),
            )
            continue
        last_entry_timestamp = entry.created_at
    if last_message_timestamp is not None:
        return _iso_from_unix_seconds(last_message_timestamp)
    return last_entry_timestamp or header.created_at


def _diagnostic_index(
    entries: list[AgentTranscriptRecord],
) -> tuple[int, str | None, str | None]:
    diagnostic_entries = [
        entry.payload
        for entry in entries
        if entry.kind == EXTENSION_DATA_KIND
        and isinstance(entry.payload, ExtensionData)
        and entry.payload.extension_type in {"diagnostic", "diagnostics"}
    ]
    if not diagnostic_entries:
        return 0, None, None

    last = diagnostic_entries[-1].data
    if isinstance(last, dict):
        code = last.get("code")
        level = last.get("level", last.get("type"))
    else:
        code = None
        level = None
    return (
        len(diagnostic_entries),
        code if isinstance(code, str) and code else None,
        level if isinstance(level, str) and level else None,
    )


def _session_index_path(session_dir: Path) -> Path:
    return session_dir / _SESSION_INDEX_FILENAME


def _path_to_text(path: Path | None) -> str | None:
    return path.as_posix() if path is not None else None


def _summary_to_index_item(summary: SessionSummary) -> dict[str, object]:
    return {
        "session_id": summary.session_id,
        "cwd": summary.cwd,
        "session_file": _path_to_text(summary.session_file),
        "parent_session": summary.parent_session,
        "leaf_id": summary.leaf_id,
        "created_at": summary.created_at,
        "updated_at": summary.updated_at,
        "name": summary.name,
        "message_count": summary.message_count,
        "entry_count": summary.entry_count,
        "first_message": summary.first_message,
        "all_messages_text": summary.all_messages_text,
        "last_message_preview": summary.last_message_preview,
        "model": dict(summary.model) if summary.model is not None else None,
        "has_diagnostics": summary.has_diagnostics,
        "diagnostic_count": summary.diagnostic_count,
        "last_diagnostic_code": summary.last_diagnostic_code,
        "last_diagnostic_level": summary.last_diagnostic_level,
    }


def _optional_path(value: object) -> Path | None:
    return Path(value) if isinstance(value, str) and value else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _model(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    provider = value.get("provider")
    model_id = value.get("model_id")
    if isinstance(provider, str) and isinstance(model_id, str):
        payload = {"provider": provider, "model_id": model_id}
        endpoint_id = value.get("endpoint_id") or value.get("endpointId")
        if isinstance(endpoint_id, str):
            payload["endpoint_id"] = endpoint_id
        return payload
    return None


def _indexed_session_file_exists(summary: SessionSummary) -> bool:
    session_file = summary.session_file
    return session_file is not None and session_file.exists()


def _summary_from_index_item(item: object) -> SessionSummary | None:
    if not isinstance(item, dict):
        return None
    session_id = _string(item.get("session_id"))
    if not session_id:
        return None
    return SessionSummary(
        session_id=session_id,
        cwd=_string(item.get("cwd")),
        session_file=_optional_path(item.get("session_file")),
        parent_session=_optional_string(item.get("parent_session")),
        leaf_id=_optional_string(item.get("leaf_id")),
        created_at=_string(item.get("created_at")),
        updated_at=_string(item.get("updated_at")),
        name=_optional_string(item.get("name")),
        message_count=_int(item.get("message_count")),
        entry_count=_int(item.get("entry_count")),
        first_message=_string(item.get("first_message")),
        all_messages_text=_string(item.get("all_messages_text")),
        last_message_preview=_optional_string(item.get("last_message_preview")),
        model=_model(item.get("model")),
        has_diagnostics=_bool(item.get("has_diagnostics")),
        diagnostic_count=_int(item.get("diagnostic_count")),
        last_diagnostic_code=_optional_string(item.get("last_diagnostic_code")),
        last_diagnostic_level=_optional_string(item.get("last_diagnostic_level")),
    )


def _decode_summary_index_item(item: object) -> SessionSummary:
    summary = _summary_from_index_item(item)
    if summary is None:
        raise ValueError("session index summary is invalid")
    return summary


def _session_projection_index(
    session_dir: Path,
) -> JsonProjectionIndex[SessionSummary]:
    return JsonProjectionIndex(
        _session_index_path(session_dir),
        version=_SESSION_INDEX_VERSION,
        items_key="summaries",
        codec=FunctionalProjectionCodec(
            encoder=_summary_to_index_item,
            decoder=_decode_summary_index_item,
        ),
        is_current=_indexed_session_file_exists,
        sort_key=lambda summary: summary.updated_at,
        reverse=True,
        generated_at=_now_iso,
    )


def build_session_context(
    entries: list[AgentTranscriptRecord],
    leaf_id: str | None | object = _LEAF_UNSET,
    by_id: dict[str, AgentTranscriptRecord] | None = None,
) -> AgentTranscriptContext:
    del by_id
    resolved_leaf_id: str | None

    if leaf_id is _LEAF_UNSET:
        resolved_leaf_id = entries[-1].record_id if entries else None
    elif leaf_id is None:
        return _AGENT_TRANSCRIPT_PROFILE.replay(())
    else:
        resolved_leaf_id = leaf_id if isinstance(leaf_id, str) else None

    if resolved_leaf_id is None:
        return _AGENT_TRANSCRIPT_PROFILE.replay(())
    conversation = ConversationRepository.create(
        header=None,
        records=entries,
        record_id=lambda entry: entry.record_id,
        parent_id=lambda entry: entry.parent_id,
        mode="compatible",
    )
    if conversation.get(resolved_leaf_id) is None:
        return _AGENT_TRANSCRIPT_PROFILE.replay(())
    conversation.branch(resolved_leaf_id)
    return _replay_session(conversation.active_records())


def _load_session_metadata(
    header: ConversationHeader,
    entries: Sequence[AgentTranscriptRecord],
) -> SessionMetadata:
    state = _AGENT_TRANSCRIPT_PROFILE.replay(entries).state
    name = _normalize_session_name(state.conversation_metadata.get("name"))
    entry_list = list(entries)
    return SessionMetadata(
        created_at=header.created_at,
        updated_at=_last_activity_timestamp(entry_list, header),
        name=name,
    )


def _project_session_summary(
    header: ConversationHeader,
    records: Sequence[AgentTranscriptRecord],
    leaf_id: str | None,
    source_path: Path | None,
) -> SessionSummary:
    entries = list(records)
    metadata = _load_session_metadata(header, entries)
    context = build_session_context(entries, leaf_id)
    last_message_preview = next(
        (
            preview
            for message in reversed(context.messages)
            if (preview := _message_preview(message))
        ),
        None,
    )
    message_texts = [
        text for message in context.messages if (text := _message_text(message))
    ]
    first_message = next(
        (
            text
            for message in context.messages
            if isinstance(message, UserMessage) and (text := _message_text(message))
        ),
        "(no messages)",
    )
    diagnostic_count, last_diagnostic_code, last_diagnostic_level = _diagnostic_index(
        entries
    )
    return SessionSummary(
        session_id=header.conversation_id,
        cwd=_header_cwd(header),
        session_file=source_path,
        parent_session=_header_parent_session(header),
        leaf_id=leaf_id,
        created_at=metadata.created_at,
        updated_at=metadata.updated_at,
        name=metadata.name,
        message_count=len(context.messages),
        entry_count=len(entries),
        first_message=first_message,
        all_messages_text=" ".join(message_texts),
        last_message_preview=last_message_preview,
        model=context.model,
        has_diagnostics=diagnostic_count > 0,
        diagnostic_count=diagnostic_count,
        last_diagnostic_code=last_diagnostic_code,
        last_diagnostic_level=last_diagnostic_level,
    )


_SESSION_SUMMARY_PROJECTOR = FunctionalConversationProjector(_project_session_summary)


def _discover_session_repositories(
    session_dir: Path,
) -> Iterable[ConversationRepository[ConversationHeader, AgentTranscriptRecord]]:
    if not session_dir.exists():
        return
    for session_file in session_dir.glob("*.jsonl"):
        if session_file.name.endswith("-export.jsonl"):
            continue
        try:
            yield load_agent_transcript_repository(
                session_file,
                writable=False,
                persist=False,
            )
        except Exception:
            continue


def _session_catalog(
    session_dir: Path,
    *,
    indexed: bool,
) -> ConversationCatalog[ConversationHeader, AgentTranscriptRecord, SessionSummary]:
    return ConversationCatalog(
        discover=lambda: _discover_session_repositories(session_dir),
        projector=_SESSION_SUMMARY_PROJECTOR,
        index=_session_projection_index(session_dir) if indexed else None,
        skip_projection_errors=True,
    )


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
        labels_by_target_id, label_timestamps_by_target_id = _build_label_indexes(
            entries
        )
        return cls(
            session_dir=path.parent,
            cwd=_header_cwd(header),
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
        labels_by_target_id, label_timestamps_by_target_id = _build_label_indexes(
            source_entries
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
        return _load_session_metadata(self.header, self.entries)

    def get_session_record(self) -> SessionRecord:
        return SessionRecord(
            session_id=self.header.conversation_id,
            cwd=self.cwd,
            session_file=self.session_file,
            parent_session=_header_parent_session(self.header),
            leaf_id=self.leaf_id,
            metadata=self.load_metadata(),
        )

    def get_session_summary(self) -> SessionSummary:
        return _project_session_summary(
            self.header,
            self.entries,
            self.leaf_id,
            self.session_file,
        )

    def get_tree(self) -> list[SessionTreeNode[AgentTranscriptRecord]]:
        def build_node(
            node: ConversationTreeNode[AgentTranscriptRecord],
        ) -> SessionTreeNode[AgentTranscriptRecord]:
            entry = node.record
            return SessionTreeNode(
                record=entry,
                children=tuple(build_node(child) for child in node.children),
                label=self.labels_by_target_id.get(entry.record_id),
                label_timestamp=self.label_timestamps_by_target_id.get(entry.record_id),
            )

        return [build_node(node) for node in self._transcript.tree()]

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
        labels_by_target_id, label_timestamps_by_target_id = _build_label_indexes(
            branch_entries
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
        if current_session_file is not None and _same_existing_path(
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
    def list(cls, session_dir: Path) -> list[SessionRecord]:
        if not session_dir.exists():
            return []

        records: list[SessionRecord] = []
        for session_file in session_dir.glob("*.jsonl"):
            if session_file.name.endswith("-export.jsonl"):
                continue
            try:
                conversation = load_agent_transcript_repository(
                    session_file,
                    writable=False,
                    persist=False,
                )
                record = SessionRecord(
                    session_id=conversation.header.conversation_id,
                    cwd=_header_cwd(conversation.header),
                    session_file=session_file,
                    parent_session=_header_parent_session(conversation.header),
                    leaf_id=conversation.leaf_id,
                    metadata=_load_session_metadata(
                        conversation.header,
                        conversation.records,
                    ),
                )
            except Exception:
                continue
            records.append(record)

        records.sort(key=lambda record: record.metadata.updated_at, reverse=True)
        return records

    @classmethod
    def list_summaries(cls, session_dir: Path) -> list[SessionSummary]:
        if not session_dir.exists():
            return []
        return list(
            ProjectionQuery[SessionSummary](
                sort_key=lambda summary: summary.updated_at,
                reverse=True,
            ).apply(_session_catalog(session_dir, indexed=False).scan())
        )

    @classmethod
    def list_all_summaries(cls, sessions_root: Path) -> list[SessionSummary]:
        if not sessions_root.exists():
            return []

        summaries = cls.list_summaries(sessions_root)
        for child in sorted(sessions_root.iterdir(), key=lambda path: path.name):
            if not child.is_dir():
                continue
            summaries.extend(cls.list_summaries(child))

        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return summaries

    @classmethod
    async def load_summary(cls, session_file: Path) -> SessionSummary:
        return (await cls.load(session_file)).get_session_summary()

    @classmethod
    def find_sessions(
        cls, session_dir: Path, query: SessionQuery | None = None
    ) -> list[SessionSummary]:
        query = query or SessionQuery()
        summaries = cls.list_summaries(session_dir)
        return _filter_session_summaries(summaries, query)

    @classmethod
    def find_all_sessions(
        cls, sessions_root: Path, query: SessionQuery | None = None
    ) -> list[SessionSummary]:
        query = query or SessionQuery()
        return _filter_session_summaries(cls.list_all_summaries(sessions_root), query)

    @classmethod
    def index_file(cls, session_dir: Path) -> Path:
        return _session_index_path(session_dir)

    @classmethod
    def refresh_index(cls, session_dir: Path) -> list[SessionSummary]:
        session_dir.mkdir(parents=True, exist_ok=True)
        return list(_session_catalog(session_dir, indexed=True).refresh())

    @classmethod
    def load_index(cls, session_dir: Path) -> list[SessionSummary]:
        return list(cls._load_index(session_dir).projections)

    @classmethod
    def _load_index(cls, session_dir: Path) -> ProjectionIndexSnapshot[SessionSummary]:
        return _session_projection_index(session_dir).load()

    @classmethod
    def list_indexed_summaries(
        cls, session_dir: Path, *, refresh: bool = False
    ) -> list[SessionSummary]:
        return list(_session_catalog(session_dir, indexed=True).list(refresh=refresh))

    @classmethod
    def find_indexed_sessions(
        cls, session_dir: Path, query: SessionQuery | None = None
    ) -> list[SessionSummary]:
        query = query or SessionQuery()
        return _filter_session_summaries(cls.list_indexed_summaries(session_dir), query)

    @classmethod
    def refresh_all_indexes(cls, sessions_root: Path) -> list[SessionSummary]:
        if not sessions_root.exists():
            sessions_root.mkdir(parents=True, exist_ok=True)
        summaries = cls.refresh_index(sessions_root)
        for child in sorted(sessions_root.iterdir(), key=lambda path: path.name):
            if not child.is_dir():
                continue
            summaries.extend(cls.refresh_index(child))
        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return summaries

    @classmethod
    def list_all_indexed_summaries(
        cls, sessions_root: Path, *, refresh: bool = False
    ) -> list[SessionSummary]:
        if refresh:
            return cls.refresh_all_indexes(sessions_root)
        if not sessions_root.exists():
            return []
        summaries = cls.list_indexed_summaries(sessions_root)
        for child in sorted(sessions_root.iterdir(), key=lambda path: path.name):
            if not child.is_dir():
                continue
            summaries.extend(cls.list_indexed_summaries(child))
        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return summaries

    @classmethod
    def find_all_indexed_sessions(
        cls, sessions_root: Path, query: SessionQuery | None = None
    ) -> list[SessionSummary]:
        query = query or SessionQuery()
        return _filter_session_summaries(
            cls.list_all_indexed_summaries(sessions_root), query
        )


def _filter_session_summaries(
    summaries: list[SessionSummary], query: SessionQuery
) -> list[SessionSummary]:
    def matches(summary: SessionSummary) -> bool:
        if query.cwd is not None and summary.cwd != query.cwd:
            return False
        if (
            query.name is not None
            and query.name.lower() not in (summary.name or "").lower()
        ):
            return False
        if (
            query.named is not None
            and bool(_normalize_session_name(summary.name)) is not query.named
        ):
            return False
        if query.parent_session is not None and not _same_session_reference(
            summary.parent_session, query.parent_session
        ):
            return False
        if (
            query.has_diagnostics is not None
            and summary.has_diagnostics is not query.has_diagnostics
        ):
            return False
        if query.text is not None and _session_query_score(summary, query.text) is None:
            return False
        return True

    sort_key = None
    reverse = False
    if query.sort_by == "relevance" and query.text is not None:

        def relevance_sort_key(summary: SessionSummary) -> tuple[int, str]:
            return (
                _session_query_score(summary, query.text) or 0,
                summary.updated_at,
            )

        sort_key = relevance_sort_key
        reverse = True
    return list(
        ProjectionQuery(
            predicate=matches,
            sort_key=sort_key,
            reverse=reverse,
            limit=query.limit,
        ).apply(summaries)
    )


def _session_haystack(summary: SessionSummary) -> str:
    return " ".join(
        value
        for value in (
            summary.session_id,
            summary.cwd,
            summary.name or "",
            summary.first_message,
            summary.all_messages_text,
            summary.last_message_preview or "",
            summary.last_diagnostic_code or "",
            summary.last_diagnostic_level or "",
            summary.session_file.name if summary.session_file is not None else "",
        )
        if value
    )


def _session_query_score(summary: SessionSummary, text: str) -> int | None:
    query = text.strip()
    if not query:
        return 0
    haystack = _normalize_query_text(_session_haystack(summary))
    if query.startswith("re:"):
        try:
            match = re.search(query[3:], haystack, flags=re.IGNORECASE)
        except re.error:
            return None
        return 1000 - match.start() if match else None
    if len(query) >= 2 and query[0] == query[-1] == '"':
        needle = _normalize_query_text(query[1:-1])
    else:
        needle = _normalize_query_text(query)
    index = haystack.lower().find(needle.lower())
    return 1000 - index if index >= 0 else None


def _normalize_query_text(text: str) -> str:
    return " ".join(text.split())


def _same_session_reference(left: str | None, right: str | None) -> bool:
    if left == right:
        return True
    if not left or not right:
        return False
    return _same_existing_path(Path(left).expanduser(), Path(right).expanduser())


def _same_existing_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=True) == right.resolve(strict=True)
    except OSError:
        return left == right
