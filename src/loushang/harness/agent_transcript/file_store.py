"""Current Native Agent transcript JSONL storage over ``ConversationStore``.

This optional Agent/AI profile owns the current Loushang transcript file
format. Product code chooses a root directory and a storage provider; it does
not own JSONL codecs, locking, or native-file discovery.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from loushang.harness.agent_transcript.migration import NATIVE_CONVERSATION_VERSION
from loushang.harness.agent_transcript.profile import AgentTranscriptProfile
from loushang.harness.agent_transcript.types import AgentTranscriptRecord
from loushang.harness.conversation import (
    ConversationHeader,
    ConversationRepository,
    NativeConversationHeaderCodec,
    NativeConversationRecordCodec,
)
from loushang.harness.journal import (
    DEFAULT_JSONL_FORMAT,
    DURABLE_LOCKED_JOURNAL,
    JournalCodecError,
    JournalDiagnostic,
    JournalFileError,
    JournalLoadPolicy,
    JournalRecordCodec,
    JsonlJournal,
    JsonlSnapshot,
    LockMode,
    journal_file_lock,
)
from loushang.harness.storage import ConversationKey, FileConversationStore


class AgentTranscriptFileError(ValueError):
    """A current Native Agent transcript file could not be read safely."""

    def __init__(self, message: str, *, path: Path, code: str) -> None:
        super().__init__(message)
        self.path = path
        self.code = code


_PROFILE = AgentTranscriptProfile.default()
_NATIVE_HEADER_CODEC = NativeConversationHeaderCodec()


class _CurrentConversationHeaderCodec:
    def encode_header(self, header: ConversationHeader):
        _require_current_native_version(header)
        return _NATIVE_HEADER_CODEC.encode_header(header)

    def decode_header(self, value):
        header = _NATIVE_HEADER_CODEC.decode_header(value)
        _require_current_native_version(header)
        return header


_HEADER_CODEC = _CurrentConversationHeaderCodec()
_RECORD_CODEC = cast(
    JournalRecordCodec[AgentTranscriptRecord],
    NativeConversationRecordCodec(_PROFILE.payload_codecs),
)
_READ_LOAD_POLICY = JournalLoadPolicy(
    header="required",
    invalid_record="raise",
    partial_tail="skip",
)
_WRITABLE_LOAD_POLICY = JournalLoadPolicy(
    header="required",
    invalid_record="raise",
    partial_tail="repair",
)


@contextmanager
def agent_transcript_file_lock(path: Path, mode: LockMode) -> Iterator[None]:
    """Lock one transcript file with the current platform implementation."""

    with journal_file_lock(
        path,
        mode,
        is_windows=_is_windows,
        load_fcntl=_load_fcntl,
        load_msvcrt=_load_msvcrt,
    ):
        yield


def agent_transcript_journal(
    path: Path,
    *,
    repair_partial_tail: bool = False,
) -> JsonlJournal[ConversationHeader, AgentTranscriptRecord]:
    """Open a current Native transcript journal without legacy migration."""

    return JsonlJournal(
        path,
        record_codec=_RECORD_CODEC,
        header_codec=_HEADER_CODEC,
        format_profile=DEFAULT_JSONL_FORMAT,
        durability=DURABLE_LOCKED_JOURNAL,
        load_policy=(
            _WRITABLE_LOAD_POLICY if repair_partial_tail else _READ_LOAD_POLICY
        ),
        lock_factory=agent_transcript_file_lock,
    )


def write_agent_transcript_file(
    path: Path,
    header: ConversationHeader,
    records: list[AgentTranscriptRecord],
) -> None:
    agent_transcript_journal(path).rewrite(records, header=header)


def append_agent_transcript_record(
    path: Path,
    record: AgentTranscriptRecord,
) -> None:
    agent_transcript_journal(path).append(record)


def create_agent_transcript_repository(
    *,
    header: ConversationHeader,
    records: list[AgentTranscriptRecord],
    path: Path | None = None,
) -> ConversationRepository[ConversationHeader, AgentTranscriptRecord]:
    return ConversationRepository.create(
        header=header,
        records=records,
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        journal=agent_transcript_journal(path) if path is not None else None,
        mode="compatible",
    )


def load_agent_transcript_repository(
    path: Path,
    *,
    writable: bool = True,
    persist: bool | None = None,
) -> ConversationRepository[ConversationHeader, AgentTranscriptRecord]:
    """Load a current Native transcript without accepting legacy formats."""

    persist_to_source = writable if persist is None else persist
    if persist_to_source and not writable:
        raise ValueError("read-only transcript repositories cannot persist changes")
    try:
        journal = agent_transcript_journal(
            path,
            repair_partial_tail=persist_to_source,
        )
        if persist_to_source:
            return ConversationRepository.load(
                journal,
                record_id=lambda record: record.record_id,
                parent_id=lambda record: record.parent_id,
                mode="compatible",
                writable=True,
            )
        snapshot = journal.load()
        if snapshot.header is None:
            raise AgentTranscriptFileError(
                "Transcript file must start with a conversation header",
                path=path,
                code="missing_conversation_header",
            )
        return _create_detached_repository(
            header=snapshot.header,
            records=snapshot.records,
            path=path,
            diagnostics=snapshot.diagnostics,
            writable=writable,
        )
    except JournalFileError as exc:
        raise _agent_transcript_file_error(exc) from exc


def load_agent_transcript_file(
    path: Path,
) -> tuple[ConversationHeader, list[AgentTranscriptRecord]]:
    try:
        snapshot: JsonlSnapshot[ConversationHeader, AgentTranscriptRecord] = (
            agent_transcript_journal(path).load()
        )
    except JournalFileError as exc:
        raise _agent_transcript_file_error(exc) from exc
    if snapshot.header is None:
        raise AgentTranscriptFileError(
            "Transcript file must start with a conversation header",
            path=path,
            code="missing_conversation_header",
        )
    return snapshot.header, list(snapshot.records)


def load_current_agent_transcript_header(path: Path) -> ConversationHeader:
    """Read one current Native header without migration or file mutation."""

    try:
        snapshot = agent_transcript_journal(path).load()
    except JournalFileError as exc:
        raise _agent_transcript_file_error(exc) from exc
    if snapshot.header is None:
        raise AgentTranscriptFileError(
            "Transcript file must start with a conversation header",
            path=path,
            code="missing_conversation_header",
        )
    return snapshot.header


FilenameForKey = Callable[[ConversationKey], str]


@dataclass
class AgentTranscriptFileLayout:
    """Map transcript identities to current Native JSONL paths.

    Products own the root they select. OEMs can provide a filename function
    without replacing the codec or storage semantics.
    """

    root: Path
    filename_for_key: FilenameForKey | None = None
    _known_paths: dict[ConversationKey, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root = self.root.expanduser().resolve(strict=False)

    @property
    def namespace(self) -> str:
        return str(self.root)

    def key(self, conversation_id: str) -> ConversationKey:
        return ConversationKey(
            namespace=self.namespace,
            conversation_id=conversation_id,
        )

    def bind_path(self, key: ConversationKey, path: str | Path) -> None:
        self._require_namespace(key)
        self._known_paths[key] = Path(path).expanduser().resolve(strict=False)

    def create_path(self, key: ConversationKey) -> Path:
        self._require_namespace(key)
        self.root.mkdir(parents=True, exist_ok=True)
        known = self._known_paths.get(key)
        if known is not None:
            return known
        filename = (
            self.filename_for_key(key)
            if self.filename_for_key is not None
            else _default_filename(key)
        )
        path = self.root / filename
        self._known_paths[key] = path
        return path

    def resolve_path(self, key: ConversationKey) -> Path | None:
        self._require_namespace(key)
        known = self._known_paths.get(key)
        if known is not None and known.is_file():
            return known
        for path in self.scan_paths(key.namespace):
            try:
                candidate = self.key_for_path(key.namespace, path)
            except Exception:
                continue
            if candidate == key:
                return path
        return None

    def scan_paths(self, namespace: str) -> tuple[Path, ...]:
        if namespace != self.namespace or not self.root.is_dir():
            return ()
        return tuple(sorted(self.root.glob("*.jsonl")))

    def key_for_path(self, namespace: str, path: Path) -> ConversationKey:
        if namespace != self.namespace:
            raise ValueError("conversation key does not belong to this layout")
        key = self.key(load_current_agent_transcript_header(path).conversation_id)
        self.bind_path(key, path)
        return key

    def bind_existing_path(self, path: str | Path) -> ConversationKey:
        resolved = Path(path).expanduser().resolve(strict=False)
        return self.key_for_path(self.namespace, resolved)

    def bind_create_path(self, key: ConversationKey, path: str | Path) -> None:
        """Bind a product-selected filename before ``ConversationStore.create``."""

        self.bind_path(key, path)

    def _require_namespace(self, key: ConversationKey) -> None:
        if key.namespace != self.namespace:
            raise ValueError("conversation key does not belong to this layout")


def create_agent_transcript_file_store(
    layout: AgentTranscriptFileLayout,
) -> FileConversationStore[ConversationHeader, AgentTranscriptRecord]:
    """Build the current Native file provider for an Agent transcript profile."""

    return FileConversationStore(
        create_path=layout.create_path,
        resolve_path=layout.resolve_path,
        scan_paths=layout.scan_paths,
        key_for_path=layout.key_for_path,
        journal_factory=agent_transcript_journal,
        record_id=lambda record: record.record_id,
    )


def _create_detached_repository(
    *,
    header: ConversationHeader,
    records: tuple[AgentTranscriptRecord, ...],
    path: Path,
    diagnostics: tuple[JournalDiagnostic, ...] = (),
    writable: bool,
) -> ConversationRepository[ConversationHeader, AgentTranscriptRecord]:
    return ConversationRepository.create(
        header=header,
        records=records,
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        mode="compatible",
        diagnostics=diagnostics,
        source_path=path,
        writable=writable,
    )


def _require_current_native_version(header: ConversationHeader) -> None:
    if header.version != NATIVE_CONVERSATION_VERSION:
        raise JournalCodecError(
            "Native Conversation version is unsupported",
            code="unsupported_native_conversation_version",
        )


def _agent_transcript_file_error(error: JournalFileError) -> AgentTranscriptFileError:
    code = {
        "empty_journal": "empty_session_file",
        "invalid_header_json": "invalid_session_header_json",
        "invalid_header_shape": "invalid_session_header",
        "invalid_envelope_type": "unsupported_session_format",
        "unsupported_native_conversation_version": "unsupported_session_format",
    }.get(error.code, error.code)
    message = {
        "empty_session_file": "Transcript file is empty",
        "invalid_session_header_json": "Transcript file header is not valid JSON",
        "missing_conversation_header": (
            "Transcript file must start with a conversation header"
        ),
        "invalid_session_header": "Transcript file header is invalid",
        "unsupported_session_format": "Transcript file format is not supported",
    }.get(code, "Transcript file is invalid")
    return AgentTranscriptFileError(message, path=error.path, code=code)


def _default_filename(key: ConversationKey) -> str:
    timestamp = (
        datetime.now(UTC)
        .isoformat()
        .replace("+00:00", "Z")
        .replace(":", "-")
        .replace(".", "-")
    )
    return f"{timestamp}_{key.conversation_id}.jsonl"


def _is_windows() -> bool:
    return os.name == "nt"


def _load_fcntl() -> Any:
    return importlib.import_module("fcntl")


def _load_msvcrt() -> Any:
    return importlib.import_module("msvcrt")


__all__ = [
    "AgentTranscriptFileError",
    "AgentTranscriptFileLayout",
    "FilenameForKey",
    "LockMode",
    "agent_transcript_file_lock",
    "agent_transcript_journal",
    "append_agent_transcript_record",
    "create_agent_transcript_file_store",
    "create_agent_transcript_repository",
    "load_agent_transcript_file",
    "load_agent_transcript_repository",
    "load_current_agent_transcript_header",
    "write_agent_transcript_file",
]
