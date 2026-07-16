from __future__ import annotations

from pathlib import Path

from loushang.coding.store.file_lock import session_file_lock
from loushang.harness.agent_transcript import (
    AgentTranscriptProfile,
    AgentTranscriptRecord,
    SessionV3MigrationError,
    is_native_conversation_file,
    migrate_session_v3_file,
    read_session_v3_file,
)
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
    JsonlJournal,
    JsonlSnapshot,
)


class SessionFileError(ValueError):
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
_RECORD_CODEC = NativeConversationRecordCodec(_PROFILE.payload_codecs)
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


def session_journal(
    path: Path,
    *,
    repair_partial_tail: bool = False,
) -> JsonlJournal[ConversationHeader, AgentTranscriptRecord]:
    return JsonlJournal(
        path,
        record_codec=_RECORD_CODEC,
        header_codec=_HEADER_CODEC,
        format_profile=DEFAULT_JSONL_FORMAT,
        durability=DURABLE_LOCKED_JOURNAL,
        load_policy=(
            _WRITABLE_LOAD_POLICY if repair_partial_tail else _READ_LOAD_POLICY
        ),
        lock_factory=session_file_lock,
    )


def write_session_file(
    path: Path,
    header: ConversationHeader,
    records: list[AgentTranscriptRecord],
) -> None:
    session_journal(path).rewrite(records, header=header)


def append_session_entry(path: Path, record: AgentTranscriptRecord) -> None:
    session_journal(path).append(record)


def create_session_repository(
    *,
    header: ConversationHeader,
    entries: list[AgentTranscriptRecord],
    path: Path | None = None,
) -> ConversationRepository[ConversationHeader, AgentTranscriptRecord]:
    return ConversationRepository.create(
        header=header,
        records=entries,
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        journal=session_journal(path) if path is not None else None,
        mode="compatible",
    )


def load_session_repository(
    path: Path,
    *,
    writable: bool = True,
    persist: bool | None = None,
) -> ConversationRepository[ConversationHeader, AgentTranscriptRecord]:
    persist_to_source = writable if persist is None else persist
    if persist_to_source and not writable:
        raise ValueError("read-only session repositories cannot persist changes")
    if not persist_to_source and not is_native_conversation_file(path):
        try:
            result = read_session_v3_file(path)
        except SessionV3MigrationError as exc:
            raise _migration_file_error(exc, path=path) from exc
        return _create_detached_repository(
            header=result.header,
            records=result.records,
            path=path,
            writable=writable,
        )
    if persist_to_source:
        _migrate_legacy_session(path)
    try:
        journal = session_journal(
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
            raise SessionFileError(
                "Session file must start with a conversation header",
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
        raise _session_file_error(exc) from exc


def _migrate_legacy_session(path: Path) -> None:
    if is_native_conversation_file(path):
        return
    try:
        migrate_session_v3_file(path)
    except SessionV3MigrationError as exc:
        raise _migration_file_error(exc, path=path) from exc


def load_session_file(
    path: Path,
) -> tuple[ConversationHeader, list[AgentTranscriptRecord]]:
    _migrate_legacy_session(path)
    try:
        snapshot: JsonlSnapshot[ConversationHeader, AgentTranscriptRecord] = (
            session_journal(path).load()
        )
    except JournalFileError as exc:
        raise _session_file_error(exc) from exc
    if snapshot.header is None:
        raise SessionFileError(
            "Session file must start with a conversation header",
            path=path,
            code="missing_conversation_header",
        )
    return snapshot.header, list(snapshot.records)


def _create_detached_repository(
    *,
    header: ConversationHeader,
    records: tuple[AgentTranscriptRecord, ...],
    path: Path,
    writable: bool,
    diagnostics: tuple[JournalDiagnostic, ...] = (),
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
    if header.version != 1:
        raise JournalCodecError(
            "Native Conversation version is unsupported",
            code="unsupported_native_conversation_version",
        )


def _session_file_error(error: JournalFileError) -> SessionFileError:
    code = {
        "empty_journal": "empty_session_file",
        "invalid_header_json": "invalid_session_header_json",
        "invalid_header_shape": "invalid_session_header",
        "invalid_envelope_type": "unsupported_session_format",
        "unsupported_native_conversation_version": "unsupported_session_format",
    }.get(error.code, error.code)
    message = {
        "empty_session_file": "Session file is empty",
        "invalid_session_header_json": "Session file header is not valid JSON",
        "missing_conversation_header": (
            "Session file must start with a conversation header"
        ),
        "invalid_session_header": "Session file header is invalid",
        "unsupported_session_format": "Session file format is not supported",
    }.get(code, "Session file is invalid")
    return SessionFileError(message, path=error.path, code=code)


def _migration_file_error(
    error: SessionV3MigrationError,
    *,
    path: Path,
) -> SessionFileError:
    code = {
        "unsupported_conversation_format": "unsupported_session_format",
        "unsupported_native_conversation_version": "unsupported_session_format",
        "unsupported_session_version": "unsupported_session_format",
    }.get(error.code, error.code)
    return SessionFileError(str(error), path=path, code=code)


__all__ = [
    "SessionFileError",
    "append_session_entry",
    "create_session_repository",
    "load_session_file",
    "load_session_repository",
    "session_journal",
    "write_session_file",
]
