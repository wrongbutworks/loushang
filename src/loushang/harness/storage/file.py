from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Generic, TypeVar

from loushang.harness.journal import (
    JournalFileError,
    JsonlJournal,
    append_jsonl_record,
    journal_file_lock,
    load_jsonl,
    write_jsonl,
)
from loushang.harness.storage.errors import (
    StoreAlreadyExistsError,
    StoreConflictError,
    StoreDataError,
    StoreNotFoundError,
)
from loushang.harness.storage.types import (
    CommitReceipt,
    ConversationKey,
    ConversationSnapshot,
    require_revision,
)

HeaderT = TypeVar("HeaderT")
RecordT = TypeVar("RecordT")
CreatePath = Callable[[ConversationKey], Path]
ResolvePath = Callable[[ConversationKey], Path | None]
ScanPaths = Callable[[str], Iterable[Path]]
KeyForPath = Callable[[str, Path], ConversationKey]
JournalFactory = Callable[[Path], JsonlJournal[HeaderT, RecordT]]
Clock = Callable[[], datetime]
RecordId = Callable[[RecordT], str | None]


class FileConversationStore(Generic[HeaderT, RecordT]):
    """File-backed Store whose layout and Native codecs are Product supplied."""

    def __init__(
        self,
        *,
        create_path: CreatePath,
        resolve_path: ResolvePath,
        scan_paths: ScanPaths,
        key_for_path: KeyForPath,
        journal_factory: JournalFactory[HeaderT, RecordT],
        clock: Clock | None = None,
        record_id: RecordId[RecordT] | None = None,
    ) -> None:
        self._create_path = create_path
        self._resolve_path = resolve_path
        self._scan_paths = scan_paths
        self._key_for_path = key_for_path
        self._journal_factory = journal_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._record_id = record_id

    async def create(
        self,
        key: ConversationKey,
        header: HeaderT,
        records: Sequence[RecordT] = (),
    ) -> ConversationSnapshot[HeaderT, RecordT]:
        durable_records = tuple(records)
        try:
            path = Path(self._create_path(key))
            journal = self._journal_factory(path)
            with _exclusive_lock(journal):
                if path.exists():
                    raise StoreAlreadyExistsError(
                        f"conversation {key!r} already exists"
                    )
                _write_unlocked(journal, header=header, records=durable_records)
        except StoreAlreadyExistsError:
            raise
        except Exception as exc:
            raise _data_error("create", key, exc) from exc
        return ConversationSnapshot(
            header=header,
            records=durable_records,
            revision=len(durable_records),
        )

    async def load(
        self,
        key: ConversationKey,
    ) -> ConversationSnapshot[HeaderT, RecordT]:
        path = self._required_path(key)
        try:
            snapshot = self._journal_factory(path).load()
        except FileNotFoundError as exc:
            raise StoreNotFoundError(f"conversation {key!r} was not found") from exc
        except Exception as exc:
            raise _data_error("load", key, exc) from exc
        if snapshot.header is None:
            raise StoreDataError(f"conversation {key!r} has no header")
        return ConversationSnapshot(
            header=snapshot.header,
            records=snapshot.records,
            revision=len(snapshot.records),
        )

    async def append(
        self,
        key: ConversationKey,
        record: RecordT,
        *,
        expected_revision: int,
    ) -> CommitReceipt:
        expected = require_revision(expected_revision, name="expected revision")
        path = self._required_path(key)
        journal = self._journal_factory(path)
        receipt: CommitReceipt
        try:
            with _exclusive_lock(journal):
                if not path.is_file():
                    raise StoreNotFoundError(f"conversation {key!r} was not found")
                snapshot = _load_unlocked(journal)
                if snapshot.header is None:
                    raise StoreDataError(f"conversation {key!r} has no header")
                revision = len(snapshot.records)
                if revision != expected:
                    raise StoreConflictError(
                        f"conversation {key!r} is at revision {revision}, "
                        f"not {expected}"
                    )
                receipt = CommitReceipt(
                    revision=revision + 1,
                    committed_at=self._clock(),
                    record_id=(
                        self._record_id(record) if self._record_id is not None else None
                    ),
                )
                _append_unlocked(journal, record)
        except (StoreConflictError, StoreDataError, StoreNotFoundError):
            raise
        except FileNotFoundError as exc:
            raise StoreNotFoundError(f"conversation {key!r} was not found") from exc
        except Exception as exc:
            raise _data_error("append to", key, exc) from exc
        return receipt

    async def delete(self, key: ConversationKey) -> None:
        path = self._required_path(key)
        journal = self._journal_factory(path)
        try:
            with _exclusive_lock(journal):
                if not path.is_file():
                    raise StoreNotFoundError(f"conversation {key!r} was not found")
                path.unlink()
        except StoreNotFoundError:
            raise
        except FileNotFoundError as exc:
            raise StoreNotFoundError(f"conversation {key!r} was not found") from exc
        except Exception as exc:
            raise _data_error("delete", key, exc) from exc

    async def scan(self, namespace: str) -> tuple[ConversationKey, ...]:
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValueError("conversation namespace must be a non-empty string")
        try:
            keys = {
                key
                for path in self._scan_paths(namespace)
                if (key := self._key_for_path(namespace, Path(path))).namespace
                == namespace
            }
        except Exception as exc:
            raise StoreDataError(
                f"conversation namespace {namespace!r} could not be scanned"
            ) from exc
        return tuple(sorted(keys))

    def _required_path(self, key: ConversationKey) -> Path:
        try:
            resolved = self._resolve_path(key)
        except Exception as exc:
            raise _data_error("resolve", key, exc) from exc
        if resolved is None:
            raise StoreNotFoundError(f"conversation {key!r} was not found")
        path = Path(resolved)
        if not path.is_file():
            raise StoreNotFoundError(f"conversation {key!r} was not found")
        return path


def _exclusive_lock(
    journal: JsonlJournal[HeaderT, RecordT],
) -> AbstractContextManager[None]:
    if journal.lock_factory is not None:
        return journal.lock_factory(journal.path, "exclusive")
    return journal_file_lock(
        journal.path,
        "exclusive",
        lock_suffix=journal.durability.lock_suffix,
    )


def _unlocked_durability(journal: JsonlJournal[object, object]):
    return replace(journal.durability, locking=False)


def _load_unlocked(journal: JsonlJournal[HeaderT, RecordT]):
    return load_jsonl(
        journal.path,
        record_codec=journal.record_codec,
        header_codec=journal.header_codec,
        format_profile=journal.format_profile,
        durability=_unlocked_durability(journal),
        load_policy=journal.load_policy,
    )


def _append_unlocked(
    journal: JsonlJournal[HeaderT, RecordT],
    record: RecordT,
) -> None:
    append_jsonl_record(
        journal.path,
        record,
        record_codec=journal.record_codec,
        format_profile=journal.format_profile,
        durability=_unlocked_durability(journal),
    )


def _write_unlocked(
    journal: JsonlJournal[HeaderT, RecordT],
    *,
    header: HeaderT,
    records: Sequence[RecordT],
) -> None:
    write_jsonl(
        journal.path,
        records,
        record_codec=journal.record_codec,
        header=header,
        header_codec=journal.header_codec,
        format_profile=journal.format_profile,
        durability=_unlocked_durability(journal),
    )


def _data_error(
    action: str,
    key: ConversationKey,
    error: Exception,
) -> StoreDataError:
    detail = error.code if isinstance(error, JournalFileError) else type(error).__name__
    return StoreDataError(f"failed to {action} conversation {key!r}: {detail}")


__all__ = ["FileConversationStore"]
