from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from loushang.agent import AgentMessage
from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, UserMessage
from loushang.coding.message import (
    BranchSummaryEntry,
    BranchSummaryMessage,
    CompactionEntry,
    CompactionSummaryMessage,
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    ModelChangeEntry,
    SessionContext,
    SessionEntry,
    SessionHeader,
    SessionInfoEntry,
    SessionMessageEntry,
    SessionTreeNode,
    ThinkingLevelChangeEntry,
    create_branch_summary_message,
    create_compaction_summary_message,
    create_custom_message,
)
from loushang.coding.store.file_codec import (
    SessionFileError,
    create_session_repository,
    load_session_repository,
    session_journal,
)
from loushang.coding.store.types import (
    SessionMetadata,
    SessionQuery,
    SessionRecord,
    SessionSummary,
)
from loushang.harness.journal import (
    BranchGraph,
    FunctionalProjectionCodec,
    JsonProjectionIndex,
    ProjectionIndexSnapshot,
    TranscriptRepository,
)
from loushang.observability import get_log
from loushang.protocol import require_json_value

CURRENT_SESSION_VERSION = 3
_LEAF_UNSET = object()
_SESSION_INDEX_VERSION = 1
_SESSION_INDEX_FILENAME = ".session-index.json"
log = get_log(__name__).bind(component="SessionManager")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _generate_id() -> str:
    return uuid4().hex[:8]


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
    entries: list[SessionEntry],
) -> tuple[dict[str, str], dict[str, str]]:
    labels_by_target_id: dict[str, str] = {}
    label_timestamps_by_target_id: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, LabelEntry):
            continue
        if entry.label:
            labels_by_target_id[entry.target_id] = entry.label
            label_timestamps_by_target_id[entry.target_id] = entry.timestamp
        else:
            labels_by_target_id.pop(entry.target_id, None)
            label_timestamps_by_target_id.pop(entry.target_id, None)
    return labels_by_target_id, label_timestamps_by_target_id


def _append_visible_message(messages: list[AgentMessage], entry: SessionEntry) -> None:
    if isinstance(entry, SessionMessageEntry):
        messages.append(entry.message)
    elif isinstance(entry, CustomMessageEntry):
        messages.append(
            create_custom_message(
                custom_type=entry.custom_type,
                content=entry.content,
                display=entry.display,
                details=entry.details,
                timestamp=entry.timestamp,
            )
        )
    elif isinstance(entry, BranchSummaryEntry):
        messages.append(
            create_branch_summary_message(
                summary=entry.summary,
                from_id=entry.from_id,
                timestamp=entry.timestamp,
            )
        )


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
    if isinstance(message, CompactionSummaryMessage):
        return " ".join(message.summary.split())[:160]
    if isinstance(message, BranchSummaryMessage):
        return " ".join(message.summary.split())[:160]
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


def _last_activity_timestamp(entries: list[SessionEntry], header: SessionHeader) -> str:
    last_message_timestamp: float | None = None
    last_entry_timestamp: str | None = None
    for entry in entries:
        if not isinstance(entry, SessionMessageEntry):
            continue
        message = entry.message
        if not isinstance(message, UserMessage | AssistantMessage):
            continue
        timestamp = getattr(message, "timestamp", None)
        if isinstance(timestamp, int | float) and timestamp > 0:
            last_message_timestamp = max(
                last_message_timestamp or 0,
                _normalize_unix_timestamp_seconds(float(timestamp)),
            )
            continue
        last_entry_timestamp = entry.timestamp
    if last_message_timestamp is not None:
        return _iso_from_unix_seconds(last_message_timestamp)
    return last_entry_timestamp or header.timestamp


def _diagnostic_index(
    entries: list[SessionEntry],
) -> tuple[int, str | None, str | None]:
    diagnostic_entries: list[CustomEntry] = [
        entry
        for entry in entries
        if isinstance(entry, CustomEntry)
        and entry.custom_type in {"diagnostic", "diagnostics"}
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


def _session_graph(entries: list[SessionEntry]) -> BranchGraph[SessionEntry]:
    return BranchGraph(
        entries,
        record_id=lambda entry: entry.id,
        parent_id=lambda entry: entry.parent_id,
        mode="compatible",
    )


def build_session_context(
    entries: list[SessionEntry],
    leaf_id: str | None | object = _LEAF_UNSET,
    by_id: dict[str, SessionEntry] | None = None,
) -> SessionContext:
    del by_id
    graph = _session_graph(entries)
    resolved_leaf_id: str | None

    if leaf_id is _LEAF_UNSET:
        resolved_leaf_id = entries[-1].id if entries else None
    elif leaf_id is None:
        return SessionContext()
    else:
        resolved_leaf_id = leaf_id if isinstance(leaf_id, str) else None

    if resolved_leaf_id is None or graph.get(resolved_leaf_id) is None:
        return SessionContext()

    path = list(graph.path(resolved_leaf_id))

    thinking_level = "off"
    model: dict[str, str] | None = None
    compaction: CompactionEntry | None = None

    for entry in path:
        if isinstance(entry, ThinkingLevelChangeEntry):
            thinking_level = entry.thinking_level
        elif isinstance(entry, ModelChangeEntry):
            model = {"provider": entry.provider, "model_id": entry.model_id}
            if entry.endpoint_id:
                model["endpoint_id"] = entry.endpoint_id
        elif isinstance(entry, SessionMessageEntry) and isinstance(
            entry.message, AssistantMessage
        ):
            model = {
                "provider": entry.message.provider,
                "model_id": entry.message.model,
            }
        elif isinstance(entry, CompactionEntry):
            compaction = entry

    messages: list[AgentMessage] = []

    if compaction is None:
        for entry in path:
            _append_visible_message(messages, entry)
        return SessionContext(
            messages=messages, thinking_level=thinking_level, model=model
        )

    messages.append(
        create_compaction_summary_message(
            summary=compaction.summary,
            tokens_before=compaction.tokens_before,
            timestamp=compaction.timestamp,
        )
    )

    compaction_index = next(
        i for i, entry in enumerate(path) if entry.id == compaction.id
    )

    found_first_kept = False
    for entry in path[:compaction_index]:
        if entry.id == compaction.first_kept_entry_id:
            found_first_kept = True
        if found_first_kept:
            _append_visible_message(messages, entry)

    for entry in path[compaction_index + 1 :]:
        _append_visible_message(messages, entry)

    return SessionContext(messages=messages, thinking_level=thinking_level, model=model)


class SessionManager:
    def __init__(
        self,
        *,
        session_dir: Path,
        cwd: str,
        persist: bool,
        repository: TranscriptRepository[SessionHeader, SessionEntry],
        session_file: Path | None = None,
        labels_by_target_id: dict[str, str] | None = None,
        label_timestamps_by_target_id: dict[str, str] | None = None,
    ) -> None:
        self.session_dir = session_dir
        self.cwd = cwd
        self.persist = persist
        self._repository = repository
        self.session_file = session_file
        self.labels_by_target_id = dict(labels_by_target_id or {})
        self.label_timestamps_by_target_id = dict(label_timestamps_by_target_id or {})

    @property
    def header(self) -> SessionHeader:
        return self._repository.header

    @header.setter
    def header(self, value: SessionHeader) -> None:
        self._repository.set_header(value)

    @property
    def entries(self) -> list[SessionEntry]:
        return list(self._repository.records)

    @property
    def by_id(self) -> dict[str, SessionEntry]:
        return {entry.id: entry for entry in self._repository.records}

    @property
    def leaf_id(self) -> str | None:
        return self._repository.leaf_id

    @leaf_id.setter
    def leaf_id(self, value: str | None) -> None:
        if value is None:
            self._repository.reset_leaf()
        else:
            self._repository.select_leaf(value)

    @classmethod
    def new(
        cls,
        session_dir: Path,
        cwd: str,
        persist: bool = True,
        parent_session: str | None = None,
        session_id: str | None = None,
    ) -> SessionManager:
        resolved_session_id = _resolve_session_id(session_id)
        header = SessionHeader(
            type="session",
            version=CURRENT_SESSION_VERSION,
            id=resolved_session_id,
            timestamp=_now_iso(),
            cwd=cwd,
            parent_session=parent_session,
        )
        session_file: Path | None = None
        if persist:
            session_dir.mkdir(parents=True, exist_ok=True)
            file_timestamp = header.timestamp.replace(":", "-").replace(".", "-")
            session_file = session_dir / f"{file_timestamp}_{header.id}.jsonl"
        repository = create_session_repository(
            header=header,
            entries=[],
            path=session_file,
        )
        return cls(
            session_dir=session_dir,
            cwd=cwd,
            persist=persist,
            repository=repository,
            session_file=session_file,
        )

    @classmethod
    def load(cls, session_file: Path, persist: bool = True) -> SessionManager:
        repository = load_session_repository(session_file, writable=persist)
        header = repository.header
        entries = list(repository.records)
        labels_by_target_id, label_timestamps_by_target_id = _build_label_indexes(
            entries
        )
        return cls(
            session_dir=session_file.parent,
            cwd=header.cwd,
            persist=persist,
            repository=repository,
            session_file=session_file,
            labels_by_target_id=labels_by_target_id,
            label_timestamps_by_target_id=label_timestamps_by_target_id,
        )

    @classmethod
    def open(
        cls,
        session_file: str | Path,
        session_dir: str | Path | None = None,
        cwd_override: str | Path | None = None,
        persist: bool = True,
    ) -> SessionManager:
        path = Path(session_file)
        try:
            manager = cls.load(path, persist=persist)
        except SessionFileError:
            manager = cls._recover_session_file(
                path,
                session_dir=Path(session_dir) if session_dir is not None else None,
                cwd_override=cwd_override,
                persist=persist,
            )
        if session_dir is not None:
            manager.session_dir = Path(session_dir)
        if cwd_override is not None:
            cwd = str(cwd_override)
            manager.cwd = cwd
            manager.header = replace(manager.header, cwd=cwd)
        return manager

    @classmethod
    def _recover_session_file(
        cls,
        session_file: Path,
        *,
        session_dir: Path | None,
        cwd_override: str | Path | None,
        persist: bool,
    ) -> SessionManager:
        cwd = (
            str(cwd_override) if cwd_override is not None else str(Path.cwd().resolve())
        )
        header = SessionHeader(
            type="session",
            version=CURRENT_SESSION_VERSION,
            id=_generate_id(),
            timestamp=_now_iso(),
            cwd=cwd,
            parent_session=None,
        )
        repository = create_session_repository(
            header=header,
            entries=[],
            path=session_file if persist else None,
        )
        return cls(
            session_dir=session_dir or session_file.parent,
            cwd=cwd,
            persist=persist,
            repository=repository,
            session_file=session_file,
        )

    @classmethod
    def continue_recent(
        cls, session_dir: str | Path, cwd: str | Path, persist: bool = True
    ) -> SessionManager:
        summaries = cls.list_summaries(Path(session_dir))
        for summary in summaries:
            if summary.session_file is None:
                continue
            return cls.open(
                summary.session_file,
                session_dir=session_dir,
                cwd_override=cwd,
                persist=persist,
            )
        return cls.new(session_dir=Path(session_dir), cwd=str(cwd), persist=persist)

    @classmethod
    def in_memory(
        cls, cwd: str | Path = ".", session_id: str | None = None
    ) -> SessionManager:
        return cls.new(
            session_dir=Path(), cwd=str(cwd), persist=False, session_id=session_id
        )

    @classmethod
    def fork_from(
        cls,
        source_file: str | Path,
        target_cwd: str | Path,
        session_dir: str | Path,
        persist: bool = True,
    ) -> SessionManager:
        source = cls.load(Path(source_file), persist=False)
        header = SessionHeader(
            type="session",
            version=CURRENT_SESSION_VERSION,
            id=_generate_id(),
            timestamp=_now_iso(),
            cwd=str(target_cwd),
            parent_session=str(Path(source_file)),
        )
        target_dir = Path(session_dir)
        session_file: Path | None = None
        if persist:
            target_dir.mkdir(parents=True, exist_ok=True)
            file_timestamp = header.timestamp.replace(":", "-").replace(".", "-")
            session_file = target_dir / f"{file_timestamp}_{header.id}.jsonl"
        source_entries = source.get_entries()
        repository = create_session_repository(
            header=header,
            entries=source_entries,
            path=session_file,
        )
        labels_by_target_id, label_timestamps_by_target_id = _build_label_indexes(
            source_entries
        )
        return cls(
            session_dir=target_dir,
            cwd=str(target_cwd),
            persist=persist,
            repository=repository,
            session_file=session_file,
            labels_by_target_id=labels_by_target_id,
            label_timestamps_by_target_id=label_timestamps_by_target_id,
        )

    def get_header(self) -> SessionHeader:
        return self.header

    def get_leaf_id(self) -> str | None:
        return self.leaf_id

    def get_entry(self, entry_id: str) -> SessionEntry | None:
        return self._repository.get(entry_id)

    def get_leaf_entry(self) -> SessionEntry | None:
        return self._repository.leaf()

    def get_entries(self) -> list[SessionEntry]:
        return list(self.entries)

    def get_children(self, parent_id: str) -> list[SessionEntry]:
        return list(self._repository.children(parent_id))

    def get_label(self, entry_id: str) -> str | None:
        return self.labels_by_target_id.get(entry_id)

    def get_session_dir(self) -> Path:
        return self.session_dir

    def get_session_file(self) -> Path | None:
        return self.session_file

    def get_cwd(self) -> str:
        return self.cwd

    def is_persisted(self) -> bool:
        return self.persist and self.session_file is not None

    def load_metadata(self) -> SessionMetadata:
        name: str | None = None
        for entry in self.entries:
            if isinstance(entry, SessionInfoEntry):
                name = _normalize_session_name(entry.name)
        return SessionMetadata(
            created_at=self.header.timestamp,
            updated_at=_last_activity_timestamp(self.entries, self.header),
            name=name,
        )

    def get_session_record(self) -> SessionRecord:
        return SessionRecord(
            session_id=self.header.id,
            cwd=self.cwd,
            session_file=self.session_file,
            parent_session=self.header.parent_session,
            leaf_id=self.leaf_id,
            metadata=self.load_metadata(),
        )

    def get_session_summary(self) -> SessionSummary:
        metadata = self.load_metadata()
        context = self.build_session_context()
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
        diagnostic_count, last_diagnostic_code, last_diagnostic_level = (
            _diagnostic_index(self.entries)
        )
        return SessionSummary(
            session_id=self.header.id,
            cwd=self.cwd,
            session_file=self.session_file,
            parent_session=self.header.parent_session,
            leaf_id=self.leaf_id,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
            name=metadata.name,
            message_count=len(context.messages),
            entry_count=len(self.entries),
            first_message=first_message,
            all_messages_text=" ".join(message_texts),
            last_message_preview=last_message_preview,
            model=context.model,
            has_diagnostics=diagnostic_count > 0,
            diagnostic_count=diagnostic_count,
            last_diagnostic_code=last_diagnostic_code,
            last_diagnostic_level=last_diagnostic_level,
        )

    def get_branch(
        self, leaf_id: str | None | object = _LEAF_UNSET
    ) -> list[SessionEntry]:
        current_id: str | None
        if leaf_id is _LEAF_UNSET:
            current_id = self.leaf_id
        else:
            current_id = leaf_id if isinstance(leaf_id, str) else None

        if current_id is None:
            return []
        if self._repository.get(current_id) is None:
            raise ValueError(f"Entry {current_id} not found")
        return list(self._repository.path_to(current_id))

    def branch(self, branch_from_id: str) -> None:
        if self._repository.get(branch_from_id) is None:
            raise ValueError(f"Entry {branch_from_id} not found")
        self._repository.select_leaf(branch_from_id)

    def reset_leaf(self) -> None:
        self._repository.reset_leaf()

    def branch_with_summary(
        self,
        branch_from_id: str | None,
        summary: str,
        details: object | None = None,
        from_hook: bool | None = None,
    ) -> str:
        if branch_from_id is not None and self._repository.get(branch_from_id) is None:
            raise ValueError(f"Entry {branch_from_id} not found")
        details = require_json_value(details, name="branch_summary.details")
        self.leaf_id = branch_from_id
        return self.append_entry(
            BranchSummaryEntry(
                type="branch_summary",
                id=_generate_id(),
                parent_id=branch_from_id,
                timestamp=_now_iso(),
                from_id=branch_from_id or "root",
                summary=summary,
                details=details,
                from_hook=from_hook,
            )
        )

    def get_tree(self) -> list[SessionTreeNode]:
        def build_node(entry: SessionEntry) -> SessionTreeNode:
            node = SessionTreeNode(
                entry=entry,
                children=[],
                label=self.labels_by_target_id.get(entry.id),
                label_timestamp=self.label_timestamps_by_target_id.get(entry.id),
            )
            node.children.extend(
                build_node(child) for child in self._repository.children(entry.id)
            )
            return node

        return [build_node(entry) for entry in self._repository.roots()]

    def _record_label_entry(self, entry: LabelEntry) -> None:
        if entry.label:
            self.labels_by_target_id[entry.target_id] = entry.label
            self.label_timestamps_by_target_id[entry.target_id] = entry.timestamp
            return
        self.labels_by_target_id.pop(entry.target_id, None)
        self.label_timestamps_by_target_id.pop(entry.target_id, None)

    def append_entry(self, entry: SessionEntry) -> str:
        entry_id = self._repository.append(entry)
        if isinstance(entry, LabelEntry):
            self._record_label_entry(entry)
        return entry_id

    def append_message(self, message: AgentMessage) -> str:
        if isinstance(message, BranchSummaryMessage | CompactionSummaryMessage):
            raise ValueError(
                "Projected summary messages must be persisted through dedicated session entries, not append_message()."
            )
        return self.append_entry(
            SessionMessageEntry(
                type="message",
                id=_generate_id(),
                parent_id=self.leaf_id,
                timestamp=_now_iso(),
                message=message,
            )
        )

    def append_thinking_level_change(self, thinking_level: str) -> str:
        return self.append_entry(
            ThinkingLevelChangeEntry(
                type="thinking_level_change",
                id=_generate_id(),
                parent_id=self.leaf_id,
                timestamp=_now_iso(),
                thinking_level=thinking_level,
            )
        )

    def append_model_change(
        self,
        provider: str,
        model_id: str,
        *,
        endpoint_id: str | None = None,
    ) -> str:
        return self.append_entry(
            ModelChangeEntry(
                type="model_change",
                id=_generate_id(),
                parent_id=self.leaf_id,
                timestamp=_now_iso(),
                provider=provider,
                model_id=model_id,
                endpoint_id=endpoint_id,
            )
        )

    def append_compaction(
        self,
        summary: str,
        first_kept_entry_id: str,
        tokens_before: int,
        details: object | None = None,
        from_hook: bool | None = None,
    ) -> str:
        details = require_json_value(details, name="compaction.details")
        return self.append_entry(
            CompactionEntry(
                type="compaction",
                id=_generate_id(),
                parent_id=self.leaf_id,
                timestamp=_now_iso(),
                summary=summary,
                first_kept_entry_id=first_kept_entry_id,
                tokens_before=tokens_before,
                details=details,
                from_hook=from_hook,
            )
        )

    def append_custom_entry(self, custom_type: str, data: object | None = None) -> str:
        data = require_json_value(data, name="custom_entry.data")
        return self.append_entry(
            CustomEntry(
                type="custom",
                id=_generate_id(),
                parent_id=self.leaf_id,
                timestamp=_now_iso(),
                custom_type=custom_type,
                data=data,
            )
        )

    def append_diagnostic_metadata(
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
        return self.append_custom_entry("diagnostic", payload)

    def append_custom_message_entry(
        self,
        custom_type: str,
        content: str | list[object],
        display: bool,
        details: object | None = None,
    ) -> str:
        details = require_json_value(
            details,
            name="custom_message.details",
        )
        return self.append_entry(
            CustomMessageEntry(
                type="custom_message",
                id=_generate_id(),
                parent_id=self.leaf_id,
                timestamp=_now_iso(),
                custom_type=custom_type,
                content=content,
                details=details,
                display=display,
            )
        )

    def append_label(self, target_id: str, label: str | None) -> str:
        if self._repository.get(target_id) is None:
            raise ValueError(f"Entry {target_id} not found")
        return self.append_entry(
            LabelEntry(
                type="label",
                id=_generate_id(),
                parent_id=self.leaf_id,
                timestamp=_now_iso(),
                target_id=target_id,
                label=_normalize_label(label),
            )
        )

    def append_session_info(self, name: str | None) -> str:
        return self.append_entry(
            SessionInfoEntry(
                type="session_info",
                id=_generate_id(),
                parent_id=self.leaf_id,
                timestamp=_now_iso(),
                name=_normalize_session_name(name),
            )
        )

    def fork(self, leaf_id: str) -> SessionManager:
        branch_entries = self.get_branch(leaf_id)
        labels_by_target_id, label_timestamps_by_target_id = _build_label_indexes(
            branch_entries
        )
        parent_session = (
            str(self.session_file) if self.session_file is not None else None
        )
        header = SessionHeader(
            type="session",
            version=CURRENT_SESSION_VERSION,
            id=_generate_id(),
            timestamp=_now_iso(),
            cwd=self.cwd,
            parent_session=parent_session,
        )

        session_file: Path | None = None
        if self.persist:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            file_timestamp = header.timestamp.replace(":", "-").replace(".", "-")
            session_file = self.session_dir / f"{file_timestamp}_{header.id}.jsonl"
        repository = self._repository.fork(
            header=header,
            journal=session_journal(session_file) if session_file is not None else None,
            leaf_id=leaf_id,
        )

        return SessionManager(
            session_dir=self.session_dir,
            cwd=self.cwd,
            persist=self.persist,
            repository=repository,
            session_file=session_file,
            labels_by_target_id=labels_by_target_id,
            label_timestamps_by_target_id=label_timestamps_by_target_id,
        )

    def create_branched_session(self, leaf_id: str) -> Path | None:
        return self.fork(leaf_id).session_file

    def build_session_context(self) -> SessionContext:
        return build_session_context(self.entries, self.leaf_id, self.by_id)

    @classmethod
    def rename_session(
        cls, session_file: str | Path, name: str | None
    ) -> SessionSummary:
        manager = cls.open(session_file, persist=True)
        manager.append_session_info(name)
        summary = manager.get_session_summary()
        cls._refresh_index_if_present(Path(session_file).expanduser().parent)
        return summary

    @classmethod
    def delete_session(
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
        if not target.exists():
            return False
        target.unlink()
        lock_file = target.with_name(f"{target.name}.lock")
        with suppress(FileNotFoundError):
            lock_file.unlink()
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
                record = cls.load(session_file).get_session_record()
            except Exception:
                continue
            records.append(record)

        records.sort(key=lambda record: record.metadata.updated_at, reverse=True)
        return records

    @classmethod
    def list_summaries(cls, session_dir: Path) -> list[SessionSummary]:
        if not session_dir.exists():
            return []

        summaries: list[SessionSummary] = []
        for session_file in session_dir.glob("*.jsonl"):
            if session_file.name.endswith("-export.jsonl"):
                continue
            try:
                summary = cls.load(session_file).get_session_summary()
            except Exception:
                continue
            summaries.append(summary)

        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return summaries

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
    def load_summary(cls, session_file: Path) -> SessionSummary:
        return cls.load(session_file).get_session_summary()

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
        return list(
            _session_projection_index(session_dir).write(
                cls.list_summaries(session_dir)
            )
        )

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
        return list(
            _session_projection_index(session_dir).load_or_refresh(
                lambda: cls.list_summaries(session_dir),
                refresh=refresh,
            )
        )

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

    filtered = [summary for summary in summaries if matches(summary)]
    if query.sort_by == "relevance" and query.text is not None:
        filtered.sort(
            key=lambda summary: (
                _session_query_score(summary, query.text) or 0,
                summary.updated_at,
            ),
            reverse=True,
        )
    if query.limit is not None:
        if query.limit < 0:
            raise ValueError("Session query limit must be non-negative")
        return filtered[: query.limit]
    return filtered


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
