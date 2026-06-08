from __future__ import annotations

import json
import os
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


class SessionFileError(ValueError):
    def __init__(self, message: str, *, path: Path, code: str) -> None:
        super().__init__(message)
        self.path = path
        self.code = code


def _serialize_header(header: SessionHeader) -> dict[str, Any]:
    return serialize_session_header(header)


def _deserialize_header(payload: dict[str, Any]) -> SessionHeader:
    return deserialize_session_header(payload)


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
        data["content"] = [serialize_content_part(part) for part in content] if isinstance(content, list) else content
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


def _deserialize_entry(payload: dict[str, Any]) -> SessionEntry:
    common = {
        "type": payload["type"],
        "id": payload["id"],
        "parent_id": payload.get("parentId"),
        "timestamp": payload["timestamp"],
    }
    entry_type = payload["type"]
    if entry_type == "message":
        return SessionMessageEntry(message=deserialize_agent_message(payload["message"]), **common)
    if entry_type == "thinking_level_change":
        return ThinkingLevelChangeEntry(thinking_level=payload["thinkingLevel"], **common)
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
        return CustomEntry(custom_type=payload["customType"], data=payload.get("data"), **common)
    if entry_type == "custom_message":
        content = payload["content"]
        return CustomMessageEntry(
            custom_type=payload["customType"],
            content=[deserialize_content_part(part) for part in content] if isinstance(content, list) else content,
            details=payload.get("details"),
            display=payload["display"],
            **common,
        )
    if entry_type == "label":
        return LabelEntry(target_id=payload["targetId"], label=payload.get("label"), **common)
    if entry_type == "session_info":
        return SessionInfoEntry(name=payload.get("name"), **common)
    raise ValueError(f"Unsupported session entry type: {entry_type}")


def write_session_file(path: Path, header: SessionHeader, entries: list[SessionEntry]) -> None:
    lines = [json.dumps(_serialize_header(header))]
    lines.extend(json.dumps(_serialize_entry(entry)) for entry in entries)
    data = "\n".join(lines) + "\n"
    with session_file_lock(path, "exclusive"):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)


def append_session_entry(path: Path, entry: SessionEntry) -> None:
    line = json.dumps(_serialize_entry(entry)) + "\n"
    with session_file_lock(path, "exclusive"):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def load_session_file(path: Path) -> tuple[SessionHeader, list[SessionEntry]]:
    with session_file_lock(path, "shared"):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise SessionFileError("Session file is empty", path=path, code="empty_session_file")

    try:
        first = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise SessionFileError(
            "Session file header is not valid JSON",
            path=path,
            code="invalid_session_header_json",
        ) from exc
    if first.get("type") != "session":
        raise SessionFileError(
            "Session file must start with a session header",
            path=path,
            code="missing_session_header",
        )

    try:
        header = _deserialize_header(first)
    except Exception as exc:
        raise SessionFileError(
            "Session file header is invalid",
            path=path,
            code="invalid_session_header",
        ) from exc
    entries: list[SessionEntry] = []
    for line in lines[1:]:
        try:
            entries.append(_deserialize_entry(json.loads(line)))
        except Exception:
            continue
    return header, entries
