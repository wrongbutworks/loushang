from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from loushang.coding.store.file_codec import (
    load_current_session_header,
    session_journal,
)
from loushang.harness.agent_transcript import AgentTranscriptRecord
from loushang.harness.conversation import ConversationHeader
from loushang.harness.storage import ConversationKey, FileConversationStore


@dataclass
class CodingSessionFileLayout:
    """Coding-owned mapping between conversation identities and local files."""

    session_dir: Path
    _known_paths: dict[ConversationKey, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.session_dir = self.session_dir.expanduser().resolve(strict=False)

    @property
    def namespace(self) -> str:
        return str(self.session_dir)

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
        self.session_dir.mkdir(parents=True, exist_ok=True)
        known = self._known_paths.get(key)
        if known is not None:
            return known
        timestamp = (
            datetime.now(UTC)
            .isoformat()
            .replace("+00:00", "Z")
            .replace(":", "-")
            .replace(".", "-")
        )
        path = self.session_dir / f"{timestamp}_{key.conversation_id}.jsonl"
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
        if namespace != self.namespace or not self.session_dir.is_dir():
            return ()
        return tuple(sorted(self.session_dir.glob("*.jsonl")))

    def key_for_path(self, namespace: str, path: Path) -> ConversationKey:
        if namespace != self.namespace:
            raise ValueError("session file namespace does not match its layout")
        header = load_current_session_header(path)
        key = self.key(header.conversation_id)
        self.bind_path(key, path)
        return key

    def bind_existing_path(self, path: str | Path) -> ConversationKey:
        resolved = Path(path).expanduser().resolve(strict=False)
        return self.key_for_path(self.namespace, resolved)

    def bind_create_path(self, key: ConversationKey, path: str | Path) -> None:
        """Bind the Product-selected filename before Store.create()."""

        self.bind_path(key, path)

    def _require_namespace(self, key: ConversationKey) -> None:
        if key.namespace != self.namespace:
            raise ValueError("conversation key does not belong to this session layout")


def create_coding_file_store(
    layout: CodingSessionFileLayout,
) -> FileConversationStore[ConversationHeader, AgentTranscriptRecord]:
    return FileConversationStore(
        create_path=layout.create_path,
        resolve_path=layout.resolve_path,
        scan_paths=layout.scan_paths,
        key_for_path=layout.key_for_path,
        journal_factory=session_journal,
        record_id=lambda record: record.record_id,
    )


__all__ = ["CodingSessionFileLayout", "create_coding_file_store"]
