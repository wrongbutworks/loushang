from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loushang.coding.message import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    ModelChangeEntry,
    SessionEntry,
    SessionHeader,
    SessionInfoEntry,
    SessionMessageEntry,
    ThinkingLevelChangeEntry,
)
from loushang.coding.message.json_codec import (
    deserialize_agent_message,
    deserialize_content_part,
    deserialize_session_header,
    serialize_agent_message,
    serialize_content_part,
    serialize_session_header,
)
from loushang.coding.store.file_lock import session_file_lock
from loushang.harness.journal import (
    DEFAULT_JSONL_FORMAT,
    DURABLE_LOCKED_JOURNAL,
    FunctionalJournalHeaderCodec,
    FunctionalJournalRecordCodec,
    JournalCodecError,
    JournalFileError,
    JournalLoadPolicy,
    JsonlJournal,
    JsonlSnapshot,
    TranscriptRepository,
)


class SessionFileError(ValueError):
    def __init__(self, message: str, *, path: Path, code: str) -> None:
        super().__init__(message)
        self.path = path
        self.code = code


def _serialize_header(header: SessionHeader) -> dict[str, Any]:
    return serialize_session_header(header)


def _deserialize_header(payload: Mapping[str, object]) -> SessionHeader:
    if payload.get("type") != "session":
        raise JournalCodecError(
            "Session file must start with a session header",
            code="missing_session_header",
        )
    try:
        return deserialize_session_header(dict(payload))
    except Exception as exc:
        raise JournalCodecError(
            "Session file header is invalid",
            code="invalid_session_header",
        ) from exc


_HEADER_CODEC = FunctionalJournalHeaderCodec(_serialize_header, _deserialize_header)
_LOAD_POLICY = JournalLoadPolicy(
    header="required",
    invalid_record="skip",
    partial_tail="skip",
)


def _base_entry_fields(entry: SessionEntry) -> dict[str, Any]:
    return {
        "type": entry.type,
        "id": entry.id,
        "parentId": entry.parent_id,
        "timestamp": entry.timestamp,
    }


def _serialize_entry(entry: SessionEntry) -> dict[str, Any]:
    data = _base_entry_fields(entry)
    if isinstance(entry, SessionMessageEntry):
        data["message"] = serialize_agent_message(entry.message)
        return data
    if isinstance(entry, ThinkingLevelChangeEntry):
        data["thinkingLevel"] = entry.thinking_level
        return data
    if isinstance(entry, ModelChangeEntry):
        data["provider"] = entry.provider
        data["modelId"] = entry.model_id
        if entry.endpoint_id:
            data["endpointId"] = entry.endpoint_id
        return data
    if isinstance(entry, CompactionEntry):
        data["summary"] = entry.summary
        data["firstKeptEntryId"] = entry.first_kept_entry_id
        data["tokensBefore"] = entry.tokens_before
        data["details"] = entry.details
        data["fromHook"] = entry.from_hook
        return data
    if isinstance(entry, BranchSummaryEntry):
        data["fromId"] = entry.from_id
        data["summary"] = entry.summary
        data["details"] = entry.details
        data["fromHook"] = entry.from_hook
        return data
    if isinstance(entry, CustomEntry):
        data["customType"] = entry.custom_type
        data["data"] = entry.data
        return data
    if isinstance(entry, CustomMessageEntry):
        data["customType"] = entry.custom_type
        content = entry.content
        data["content"] = (
            [serialize_content_part(part) for part in content]
            if isinstance(content, list)
            else content
        )
        data["details"] = entry.details
        data["display"] = entry.display
        return data
    if isinstance(entry, LabelEntry):
        data["targetId"] = entry.target_id
        data["label"] = entry.label
        return data
    if isinstance(entry, SessionInfoEntry):
        data["name"] = entry.name
        return data
    raise ValueError(f"Unsupported session entry type: {type(entry)!r}")


def _deserialize_entry(payload: Mapping[str, object]) -> SessionEntry:
    common = {
        "type": payload["type"],
        "id": payload["id"],
        "parent_id": payload.get("parentId"),
        "timestamp": payload["timestamp"],
    }
    entry_type = payload["type"]
    if entry_type == "message":
        return SessionMessageEntry(
            message=deserialize_agent_message(payload["message"]), **common
        )
    if entry_type == "thinking_level_change":
        return ThinkingLevelChangeEntry(
            thinking_level=payload["thinkingLevel"], **common
        )
    if entry_type == "model_change":
        return ModelChangeEntry(
            provider=payload["provider"],
            model_id=payload["modelId"],
            endpoint_id=payload.get("endpointId"),
            **common,
        )
    if entry_type == "compaction":
        return CompactionEntry(
            summary=payload["summary"],
            first_kept_entry_id=payload["firstKeptEntryId"],
            tokens_before=payload["tokensBefore"],
            details=payload.get("details"),
            from_hook=payload.get("fromHook"),
            **common,
        )
    if entry_type == "branch_summary":
        return BranchSummaryEntry(
            from_id=payload["fromId"],
            summary=payload["summary"],
            details=payload.get("details"),
            from_hook=payload.get("fromHook"),
            **common,
        )
    if entry_type == "custom":
        return CustomEntry(
            custom_type=payload["customType"], data=payload.get("data"), **common
        )
    if entry_type == "custom_message":
        content = payload["content"]
        return CustomMessageEntry(
            custom_type=payload["customType"],
            content=[deserialize_content_part(part) for part in content]
            if isinstance(content, list)
            else content,
            details=payload.get("details"),
            display=payload["display"],
            **common,
        )
    if entry_type == "label":
        return LabelEntry(
            target_id=payload["targetId"], label=payload.get("label"), **common
        )
    if entry_type == "session_info":
        return SessionInfoEntry(name=payload.get("name"), **common)
    raise ValueError(f"Unsupported session entry type: {entry_type}")


_ENTRY_CODEC = FunctionalJournalRecordCodec(_serialize_entry, _deserialize_entry)


def session_journal(path: Path) -> JsonlJournal[SessionHeader, SessionEntry]:
    return JsonlJournal(
        path,
        record_codec=_ENTRY_CODEC,
        header_codec=_HEADER_CODEC,
        format_profile=DEFAULT_JSONL_FORMAT,
        durability=DURABLE_LOCKED_JOURNAL,
        load_policy=_LOAD_POLICY,
        lock_factory=session_file_lock,
    )


def write_session_file(
    path: Path, header: SessionHeader, entries: list[SessionEntry]
) -> None:
    session_journal(path).rewrite(entries, header=header)


def append_session_entry(path: Path, entry: SessionEntry) -> None:
    session_journal(path).append(entry)


def create_session_repository(
    *,
    header: SessionHeader,
    entries: list[SessionEntry],
    path: Path | None = None,
) -> TranscriptRepository[SessionHeader, SessionEntry]:
    return TranscriptRepository.create(
        header=header,
        records=entries,
        record_id=lambda entry: entry.id,
        parent_id=lambda entry: entry.parent_id,
        journal=session_journal(path) if path is not None else None,
        mode="compatible",
    )


def load_session_repository(
    path: Path,
    *,
    writable: bool = True,
) -> TranscriptRepository[SessionHeader, SessionEntry]:
    try:
        return TranscriptRepository.load(
            session_journal(path),
            record_id=lambda entry: entry.id,
            parent_id=lambda entry: entry.parent_id,
            mode="compatible",
            writable=writable,
        )
    except JournalFileError as exc:
        raise _session_file_error(exc) from exc


def load_session_file(path: Path) -> tuple[SessionHeader, list[SessionEntry]]:
    try:
        snapshot: JsonlSnapshot[SessionHeader, SessionEntry] = session_journal(
            path
        ).load()
    except JournalFileError as exc:
        raise _session_file_error(exc) from exc
    if snapshot.header is None:
        raise SessionFileError(
            "Session file must start with a session header",
            path=path,
            code="missing_session_header",
        )
    return snapshot.header, list(snapshot.records)


def _session_file_error(error: JournalFileError) -> SessionFileError:
    code = {
        "empty_journal": "empty_session_file",
        "invalid_header_json": "invalid_session_header_json",
        "invalid_header_shape": "invalid_session_header",
    }.get(error.code, error.code)
    message = {
        "empty_session_file": "Session file is empty",
        "invalid_session_header_json": "Session file header is not valid JSON",
        "missing_session_header": "Session file must start with a session header",
        "invalid_session_header": "Session file header is invalid",
    }.get(code, "Session file is invalid")
    return SessionFileError(message, path=error.path, code=code)
