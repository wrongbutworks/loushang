"""Catalog, summaries, and query helpers for current Agent transcripts.

This optional Agent/AI profile projects current Native transcripts into a
portable session read model. Products choose their roots and presentation, but
do not need to recreate native discovery, summary indexing, or query logic.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

from loushang.agent.types import AgentMessage
from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, UserMessage
from loushang.harness.agent_transcript.kinds import (
    AGENT_MESSAGE_KIND,
    EXTENSION_DATA_KIND,
    RECORD_ANNOTATION_PATCH_KIND,
)
from loushang.harness.agent_transcript.native_file import (
    AgentTranscriptFileLayout,
    create_agent_transcript_file_store,
)
from loushang.harness.agent_transcript.profile import AgentTranscriptProfile
from loushang.harness.agent_transcript.types import (
    AgentTranscriptContext,
    AgentTranscriptRecord,
    ApplicationMessage,
    ExtensionData,
    RecordAnnotationPatch,
)
from loushang.harness.conversation import (
    ConversationCatalog,
    ConversationHeader,
    ConversationIndex,
    ConversationLocator,
    ConversationProviderBinding,
    ConversationRepository,
    ConversationTreeNode,
    FunctionalConversationProjector,
    FunctionalProjectionCodec,
    IndexedProjection,
    JsonConversationIndex,
    ProjectionQuery,
)
from loushang.observability import get_log

RecordT = TypeVar("RecordT")

_LEAF_UNSET = object()
_MISSING = object()
_SESSION_INDEX_VERSION = 1
_SESSION_INDEX_FILENAME = ".session-index.json"
_PROFILE = AgentTranscriptProfile.default()
log = get_log(__name__).bind(component="AgentTranscriptSessionCatalog")


@dataclass(frozen=True)
class SessionMetadata:
    created_at: str
    updated_at: str
    name: str | None = None


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    cwd: str
    session_file: Path | None
    parent_session: str | None
    leaf_id: str | None
    metadata: SessionMetadata
    locator: ConversationLocator | None = None


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    cwd: str
    session_file: Path | None
    parent_session: str | None
    leaf_id: str | None
    created_at: str
    updated_at: str
    name: str | None
    message_count: int
    entry_count: int
    first_message: str
    all_messages_text: str
    last_message_preview: str | None
    model: dict[str, str] | None
    has_diagnostics: bool = False
    diagnostic_count: int = 0
    last_diagnostic_code: str | None = None
    last_diagnostic_level: str | None = None
    locator: ConversationLocator | None = None


@dataclass(frozen=True, kw_only=True)
class SessionQuery:
    cwd: str | None = None
    name: str | None = None
    parent_session: str | None = None
    text: str | None = None
    named: bool | None = None
    sort_by: Literal["recent", "relevance"] = "recent"
    has_diagnostics: bool | None = None
    limit: int | None = None


@dataclass(frozen=True)
class SessionTreeNode(Generic[RecordT]):
    record: RecordT
    children: tuple["SessionTreeNode[RecordT]", ...] = ()
    label: str | None = None
    label_timestamp: str | None = None


def project_session_record(record: object) -> dict[str, object]:
    """Project a session catalog record into the portable listing shape."""

    metadata = _safe_session_getattr(record, "metadata", None)
    session_file = _safe_session_getattr(record, "session_file", None)
    if metadata is not None:
        normalized = {
            "session_id": _session_string_attr(record, "session_id"),
            "cwd": _session_string_attr(record, "cwd"),
            "session_file": _safe_session_string(session_file)
            if session_file is not None
            else None,
            "parent_session": _session_nullable_string_attr(record, "parent_session"),
            "leaf_id": _session_nullable_string_attr(record, "leaf_id"),
            "metadata": {
                "created_at": _session_string_attr(metadata, "created_at"),
                "updated_at": _session_string_attr(metadata, "updated_at"),
                "name": _session_nullable_string_attr(metadata, "name"),
            },
        }
    else:
        normalized = {
            "session_id": _session_string_attr(record, "session_id"),
            "cwd": _session_string_attr(record, "cwd"),
            "session_file": _safe_session_string(session_file)
            if session_file is not None
            else None,
            "parent_session": _session_nullable_string_attr(record, "parent_session"),
            "leaf_id": _session_nullable_string_attr(record, "leaf_id"),
            "metadata": {
                "created_at": _session_string_attr(record, "created_at"),
                "updated_at": _session_string_attr(record, "updated_at"),
                "name": _session_nullable_string_attr(record, "name"),
            },
        }

    for field_name in (
        "message_count",
        "entry_count",
        "first_message",
        "all_messages_text",
        "last_message_preview",
        "model",
        "has_diagnostics",
        "diagnostic_count",
        "last_diagnostic_code",
        "last_diagnostic_level",
    ):
        value = _safe_session_getattr(record, field_name, _MISSING)
        if value is not _MISSING:
            normalized[field_name] = _json_safe_session_value(value)
    return normalized


def try_project_session_record(record: object) -> dict[str, object] | None:
    """Best-effort session projection for catalogs containing bad records."""

    try:
        return project_session_record(record)
    except Exception:
        return None


def _session_string_attr(target: object, name: str) -> str:
    value = _safe_session_getattr(target, name, "")
    return value if isinstance(value, str) else _safe_session_string(value)


def _session_nullable_string_attr(target: object, name: str) -> str | None:
    value = _safe_session_getattr(target, name, None)
    if value is None:
        return None
    return value if isinstance(value, str) else _safe_session_string(value)


def _safe_session_getattr(target: object, name: str, default: object) -> object:
    try:
        return getattr(target, name, default)
    except Exception:
        return default


def _safe_session_string(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        try:
            return repr(value)
        except Exception:
            return ""


def _json_safe_session_value(value: Any) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            _safe_session_string(key): _json_safe_session_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_json_safe_session_value(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return _safe_session_string(value)


def agent_transcript_header_cwd(header: ConversationHeader) -> str:
    """Return the current Native transcript workspace hint, if present."""

    cwd = header.metadata.get("cwd")
    return cwd if isinstance(cwd, str) else ""


def agent_transcript_header_parent_session(
    header: ConversationHeader,
) -> str | None:
    """Return the current Native transcript parent-session reference."""

    parent = header.metadata.get("parentSession")
    return parent if isinstance(parent, str) else None


def build_agent_transcript_label_indexes(
    records: Sequence[AgentTranscriptRecord],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build the standard display-label indexes from append-only annotations."""

    labels_by_target_id: dict[str, str] = {}
    label_timestamps_by_target_id: dict[str, str] = {}
    for record in records:
        patch = record.payload
        if record.kind != RECORD_ANNOTATION_PATCH_KIND or not isinstance(
            patch, RecordAnnotationPatch
        ):
            continue
        if patch.namespace != "display.label":
            continue
        if patch.operation == "set" and isinstance(patch.value, str):
            labels_by_target_id[patch.target_record_id] = patch.value
            label_timestamps_by_target_id[patch.target_record_id] = record.created_at
        else:
            labels_by_target_id.pop(patch.target_record_id, None)
            label_timestamps_by_target_id.pop(patch.target_record_id, None)
    return labels_by_target_id, label_timestamps_by_target_id


def build_agent_transcript_session_context(
    records: Sequence[AgentTranscriptRecord],
    leaf_id: str | None | object = _LEAF_UNSET,
    by_id: dict[str, AgentTranscriptRecord] | None = None,
) -> AgentTranscriptContext:
    """Replay one selected Native transcript branch into Agent context."""

    del by_id
    entries = list(records)
    if leaf_id is _LEAF_UNSET:
        resolved_leaf_id = entries[-1].record_id if entries else None
    elif leaf_id is None:
        return _PROFILE.replay(())
    else:
        resolved_leaf_id = leaf_id if isinstance(leaf_id, str) else None

    if resolved_leaf_id is None:
        return _PROFILE.replay(())
    conversation = ConversationRepository.create(
        header=None,
        records=entries,
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        mode="compatible",
    )
    if conversation.get(resolved_leaf_id) is None:
        return _PROFILE.replay(())
    conversation.branch(resolved_leaf_id)
    return _PROFILE.replay(conversation.active_records())


def load_agent_transcript_session_metadata(
    header: ConversationHeader,
    records: Sequence[AgentTranscriptRecord],
) -> SessionMetadata:
    state = _PROFILE.replay(records).state
    return SessionMetadata(
        created_at=header.created_at,
        updated_at=_last_activity_timestamp(records, header),
        name=_normalize_nonblank(state.conversation_metadata.get("name")),
    )


def project_agent_transcript_session_summary(
    header: ConversationHeader,
    records: Sequence[AgentTranscriptRecord],
    leaf_id: str | None,
    source_path: Path | None,
    *,
    locator: ConversationLocator | None = None,
) -> SessionSummary:
    """Project standard Agent transcript facts into one searchable summary."""

    entries = list(records)
    metadata = load_agent_transcript_session_metadata(header, entries)
    context = build_agent_transcript_session_context(entries, leaf_id)
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
        cwd=agent_transcript_header_cwd(header),
        session_file=source_path,
        parent_session=agent_transcript_header_parent_session(header),
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
        locator=locator,
    )


def build_agent_transcript_session_tree(
    nodes: Sequence[ConversationTreeNode[AgentTranscriptRecord]],
    *,
    labels_by_target_id: dict[str, str] | None = None,
    label_timestamps_by_target_id: dict[str, str] | None = None,
) -> list[SessionTreeNode[AgentTranscriptRecord]]:
    """Project a repository tree with standard display-label annotations."""

    labels = labels_by_target_id or {}
    timestamps = label_timestamps_by_target_id or {}

    def build(
        node: ConversationTreeNode[AgentTranscriptRecord],
    ) -> SessionTreeNode[AgentTranscriptRecord]:
        record = node.record
        return SessionTreeNode(
            record=record,
            children=tuple(build(child) for child in node.children),
            label=labels.get(record.record_id),
            label_timestamp=timestamps.get(record.record_id),
        )

    return [build(node) for node in nodes]


class AgentTranscriptSessionCatalog:
    """Agent projection facade over a provider-bound conversation catalog."""

    def __init__(self, session_dir: str | Path) -> None:
        self.session_dir = Path(session_dir).expanduser().resolve(strict=False)
        self._layout = AgentTranscriptFileLayout(self.session_dir)
        self._provider = ConversationProviderBinding(
            provider_id=f"agent-native-file:{self.session_dir.as_posix()}",
            namespace=self._layout.namespace,
            store=create_agent_transcript_file_store(self._layout),
        )
        self._external_index: (
            ConversationIndex[SessionSummary, SessionQuery] | None
        ) = None
        self._session_file_for: Callable[[ConversationLocator], Path | None] = (
            lambda locator: self._layout.resolve_path(locator.key)
        )

    @classmethod
    def from_provider(
        cls,
        provider: ConversationProviderBinding[
            ConversationHeader,
            AgentTranscriptRecord,
        ],
        *,
        index: ConversationIndex[SessionSummary, SessionQuery] | None = None,
        session_file_for: (
            Callable[[ConversationLocator], Path | None] | None
        ) = None,
    ) -> AgentTranscriptSessionCatalog:
        """Compose Agent projections over any registered Store provider."""

        catalog = cls.__new__(cls)
        catalog.session_dir = None
        catalog._layout = None
        catalog._provider = provider
        catalog._external_index = index
        catalog._session_file_for = session_file_for or (lambda locator: None)
        return catalog

    @property
    def index_path(self) -> Path:
        if self.session_dir is None:
            raise ValueError("provider-backed catalog has no local JSON index path")
        return self.session_dir / _SESSION_INDEX_FILENAME

    def list_records(self) -> list[SessionRecord]:
        return [
            SessionRecord(
                session_id=summary.session_id,
                cwd=summary.cwd,
                session_file=summary.session_file,
                parent_session=summary.parent_session,
                leaf_id=summary.leaf_id,
                metadata=SessionMetadata(
                    created_at=summary.created_at,
                    updated_at=summary.updated_at,
                    name=summary.name,
                ),
                locator=summary.locator,
            )
            for summary in self.list_summaries()
        ]

    def list_summaries(self) -> list[SessionSummary]:
        result = _run_catalog(self._catalog(indexed=False).scan())
        return _sort_summaries(item.projection for item in result.items)

    def find_summaries(
        self,
        query: SessionQuery | None = None,
    ) -> list[SessionSummary]:
        return filter_agent_transcript_session_summaries(
            self.list_summaries(), query or SessionQuery()
        )

    def refresh_index(self) -> list[SessionSummary]:
        if self.session_dir is not None:
            self.session_dir.mkdir(parents=True, exist_ok=True)
        result = _run_catalog(self._catalog(indexed=True).refresh())
        return _sort_summaries(item.projection for item in result.items)

    def load_index(self) -> list[SessionSummary]:
        items = _run_catalog(self._projection_index().query(SessionQuery()))
        return [
            replace(item.projection, locator=item.locator)
            for item in items
        ]

    def list_indexed_summaries(self, *, refresh: bool = False) -> list[SessionSummary]:
        if self._external_index is not None:
            summaries = self.refresh_index() if refresh else self.load_index()
            return summaries or self.refresh_index()
        if refresh or not self.index_path.exists():
            return self.refresh_index()
        summaries = self.load_index()
        if not summaries or not self.index_path.exists() or any(
            summary.session_file is None or not summary.session_file.is_file()
            for summary in summaries
        ):
            return self.refresh_index()
        return summaries

    def find_indexed_summaries(
        self,
        query: SessionQuery | None = None,
    ) -> list[SessionSummary]:
        return filter_agent_transcript_session_summaries(
            self.list_indexed_summaries(), query or SessionQuery()
        )

    def _catalog(
        self,
        *,
        indexed: bool,
    ) -> ConversationCatalog[
        ConversationHeader,
        AgentTranscriptRecord,
        SessionSummary,
        SessionQuery,
    ]:
        return ConversationCatalog(
            providers=(self._provider,),
            projector=FunctionalConversationProjector(self._project_summary),
            record_id=lambda record: record.record_id,
            index=self._projection_index() if indexed else None,
            query_items=_query_indexed_summaries,
        )

    def _project_summary(
        self,
        header: ConversationHeader,
        records: Sequence[AgentTranscriptRecord],
        leaf_id: str | None,
        locator: ConversationLocator,
    ) -> SessionSummary:
        return project_agent_transcript_session_summary(
            header,
            records,
            leaf_id,
            self._session_file_for(locator),
            locator=locator,
        )

    def _projection_index(
        self,
    ) -> ConversationIndex[SessionSummary, SessionQuery]:
        if self._external_index is not None:
            return self._external_index
        return JsonConversationIndex(
            self.index_path,
            version=_SESSION_INDEX_VERSION,
            codec=FunctionalProjectionCodec(
                encoder=_summary_to_index_item,
                decoder=_decode_summary_index_item,
            ),
            query_items=_query_indexed_summaries,
        )


def list_all_agent_transcript_session_summaries(
    sessions_root: str | Path,
) -> list[SessionSummary]:
    root = Path(sessions_root)
    if not root.exists():
        return []
    summaries = AgentTranscriptSessionCatalog(root).list_summaries()
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.is_dir():
            summaries.extend(AgentTranscriptSessionCatalog(child).list_summaries())
    summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
    return summaries


def find_all_agent_transcript_session_summaries(
    sessions_root: str | Path,
    query: SessionQuery | None = None,
) -> list[SessionSummary]:
    return filter_agent_transcript_session_summaries(
        list_all_agent_transcript_session_summaries(sessions_root),
        query or SessionQuery(),
    )


def refresh_all_agent_transcript_session_indexes(
    sessions_root: str | Path,
) -> list[SessionSummary]:
    root = Path(sessions_root)
    root.mkdir(parents=True, exist_ok=True)
    summaries = AgentTranscriptSessionCatalog(root).refresh_index()
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.is_dir():
            summaries.extend(AgentTranscriptSessionCatalog(child).refresh_index())
    summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
    return summaries


def list_all_indexed_agent_transcript_session_summaries(
    sessions_root: str | Path,
    *,
    refresh: bool = False,
) -> list[SessionSummary]:
    if refresh:
        return refresh_all_agent_transcript_session_indexes(sessions_root)
    root = Path(sessions_root)
    if not root.exists():
        return []
    summaries = AgentTranscriptSessionCatalog(root).list_indexed_summaries()
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.is_dir():
            summaries.extend(
                AgentTranscriptSessionCatalog(child).list_indexed_summaries()
            )
    summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
    return summaries


def find_all_indexed_agent_transcript_session_summaries(
    sessions_root: str | Path,
    query: SessionQuery | None = None,
) -> list[SessionSummary]:
    return filter_agent_transcript_session_summaries(
        list_all_indexed_agent_transcript_session_summaries(sessions_root),
        query or SessionQuery(),
    )


def filter_agent_transcript_session_summaries(
    summaries: Sequence[SessionSummary],
    query: SessionQuery,
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
            and bool(_normalize_nonblank(summary.name)) is not query.named
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
        query_text = query.text

        def relevance_sort_key(summary: SessionSummary) -> tuple[int, str]:
            return _session_query_score(summary, query_text) or 0, summary.updated_at

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
    if isinstance(message, ApplicationMessage) and isinstance(message.content, str):
        return " ".join(message.content.split())[:160] or None
    return None


def _message_text(message: AgentMessage) -> str | None:
    if not isinstance(message, UserMessage | AssistantMessage):
        return None
    parts = getattr(message, "content", None)
    if isinstance(parts, str):
        text = parts
    elif isinstance(parts, list):
        text = " ".join(part.text for part in parts if isinstance(part, TextPart))
    else:
        text = ""
    normalized = " ".join(text.split())
    return normalized or None


def _last_activity_timestamp(
    records: Sequence[AgentTranscriptRecord],
    header: ConversationHeader,
) -> str:
    last_message_timestamp: float | None = None
    last_record_timestamp: str | None = None
    for record in records:
        if record.kind != AGENT_MESSAGE_KIND or not isinstance(
            record.payload, UserMessage | AssistantMessage
        ):
            continue
        timestamp = getattr(record.payload, "timestamp", None)
        if isinstance(timestamp, int | float) and timestamp > 0:
            last_message_timestamp = max(
                last_message_timestamp or 0,
                _normalize_unix_timestamp_seconds(float(timestamp)),
            )
        else:
            last_record_timestamp = record.created_at
    if last_message_timestamp is not None:
        return (
            datetime.fromtimestamp(last_message_timestamp, UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return last_record_timestamp or header.created_at


def _normalize_unix_timestamp_seconds(timestamp: float) -> float:
    # Agent messages normally use milliseconds; tolerate older second values.
    if timestamp <= 32_503_680_000:
        return timestamp
    normalized = timestamp / 1000
    log.problem(
        "session_timestamp_normalized",
        severity="warning",
        source="session",
        message=(
            "Session message timestamp looked like milliseconds and was normalized "
            "to seconds."
        ),
        recoverable=True,
        original_timestamp=timestamp,
        normalized_timestamp=normalized,
        unit="milliseconds",
    )
    return normalized


def _diagnostic_index(
    records: Sequence[AgentTranscriptRecord],
) -> tuple[int, str | None, str | None]:
    diagnostics = [
        record.payload
        for record in records
        if record.kind == EXTENSION_DATA_KIND
        and isinstance(record.payload, ExtensionData)
        and record.payload.extension_type in {"diagnostic", "diagnostics"}
    ]
    if not diagnostics:
        return 0, None, None
    last = diagnostics[-1].data
    code = last.get("code") if isinstance(last, dict) else None
    level = last.get("level", last.get("type")) if isinstance(last, dict) else None
    return (
        len(diagnostics),
        code if isinstance(code, str) and code else None,
        level if isinstance(level, str) and level else None,
    )


def _summary_to_index_item(summary: SessionSummary) -> dict[str, object]:
    return {
        "session_id": summary.session_id,
        "cwd": summary.cwd,
        "session_file": summary.session_file.as_posix()
        if summary.session_file is not None
        else None,
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


def _decode_summary_index_item(value: Mapping[str, object]) -> SessionSummary:
    session_id = _string(value.get("session_id"))
    if not session_id:
        raise ValueError("session index summary is invalid")
    return SessionSummary(
        session_id=session_id,
        cwd=_string(value.get("cwd")),
        session_file=_optional_path(value.get("session_file")),
        parent_session=_optional_string(value.get("parent_session")),
        leaf_id=_optional_string(value.get("leaf_id")),
        created_at=_string(value.get("created_at")),
        updated_at=_string(value.get("updated_at")),
        name=_optional_string(value.get("name")),
        message_count=_int(value.get("message_count")),
        entry_count=_int(value.get("entry_count")),
        first_message=_string(value.get("first_message")),
        all_messages_text=_string(value.get("all_messages_text")),
        last_message_preview=_optional_string(value.get("last_message_preview")),
        model=_model(value.get("model")),
        has_diagnostics=_bool(value.get("has_diagnostics")),
        diagnostic_count=_int(value.get("diagnostic_count")),
        last_diagnostic_code=_optional_string(value.get("last_diagnostic_code")),
        last_diagnostic_level=_optional_string(value.get("last_diagnostic_level")),
    )


def _indexed_session_file_exists(summary: SessionSummary) -> bool:
    return summary.session_file is not None and summary.session_file.exists()


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
    needle = (
        _normalize_query_text(query[1:-1])
        if len(query) >= 2 and query[0] == query[-1] == '"'
        else _normalize_query_text(query)
    )
    index = haystack.lower().find(needle.lower())
    return 1000 - index if index >= 0 else None


def _normalize_nonblank(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _normalize_query_text(text: str) -> str:
    return " ".join(text.split())


def _same_session_reference(left: str | None, right: str | None) -> bool:
    if left == right:
        return True
    if not left or not right:
        return False
    return same_agent_transcript_session_path(
        Path(left).expanduser(), Path(right).expanduser()
    )


def same_agent_transcript_session_path(left: Path, right: Path) -> bool:
    """Compare canonical existing transcript paths without requiring existence."""

    try:
        return left.resolve(strict=True) == right.resolve(strict=True)
    except OSError:
        return left == right


def _optional_path(value: object) -> Path | None:
    return Path(value) if isinstance(value, str) and value else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _model(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    provider = value.get("provider")
    model_id = value.get("model_id")
    if not isinstance(provider, str) or not isinstance(model_id, str):
        return None
    result = {"provider": provider, "model_id": model_id}
    endpoint_id = value.get("endpoint_id") or value.get("endpointId")
    if isinstance(endpoint_id, str):
        result["endpoint_id"] = endpoint_id
    return result


def _sort_summaries(summaries) -> list[SessionSummary]:
    return sorted(summaries, key=lambda summary: summary.updated_at, reverse=True)


def _query_indexed_summaries(
    query: SessionQuery,
    items: Sequence[IndexedProjection[SessionSummary]],
) -> tuple[IndexedProjection[SessionSummary], ...]:
    ordered = sorted(
        items,
        key=lambda item: item.projection.updated_at,
        reverse=True,
    )
    selected = filter_agent_transcript_session_summaries(
        [item.projection for item in ordered],
        query,
    )
    by_identity = {id(item.projection): item for item in ordered}
    return tuple(by_identity[id(summary)] for summary in selected)


def _run_catalog(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, awaitable).result()


__all__ = [
    "AgentTranscriptSessionCatalog",
    "SessionMetadata",
    "SessionQuery",
    "SessionRecord",
    "SessionSummary",
    "SessionTreeNode",
    "agent_transcript_header_cwd",
    "agent_transcript_header_parent_session",
    "build_agent_transcript_label_indexes",
    "build_agent_transcript_session_context",
    "build_agent_transcript_session_tree",
    "filter_agent_transcript_session_summaries",
    "find_all_agent_transcript_session_summaries",
    "find_all_indexed_agent_transcript_session_summaries",
    "list_all_agent_transcript_session_summaries",
    "list_all_indexed_agent_transcript_session_summaries",
    "load_agent_transcript_session_metadata",
    "project_agent_transcript_session_summary",
    "refresh_all_agent_transcript_session_indexes",
    "same_agent_transcript_session_path",
]
