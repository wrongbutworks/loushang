from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Header:
    transcript_id: str


@dataclass(frozen=True)
class _Record:
    record_id: str
    parent_id: str | None
    text: str


class _HeaderCodec:
    def encode_header(self, header: _Header):
        return {"type": "transcript", "id": header.transcript_id}

    def decode_header(self, value):
        return _Header(transcript_id=str(value["id"]))


class _RecordCodec:
    def encode_record(self, record: _Record):
        return {
            "id": record.record_id,
            "parentId": record.parent_id,
            "text": record.text,
        }

    def decode_record(self, value):
        parent_id = value.get("parentId")
        return _Record(
            record_id=str(value["id"]),
            parent_id=str(parent_id) if parent_id is not None else None,
            text=str(value["text"]),
        )


def _journal(path: Path):
    from loushang.harness.journal import JournalLoadPolicy, JsonlJournal

    return JsonlJournal(
        path,
        header_codec=_HeaderCodec(),
        record_codec=_RecordCodec(),
        load_policy=JournalLoadPolicy(header="required"),
    )


def _repository(*, header: _Header, records=(), journal=None):
    from loushang.harness.journal import TranscriptRepository

    return TranscriptRepository.create(
        header=header,
        records=records,
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        journal=journal,
    )


def test_transcript_repository_persists_active_branch_and_reload(
    tmp_path: Path,
) -> None:
    from loushang.harness.journal import TranscriptRepository

    path = tmp_path / "transcript.jsonl"
    repository = _repository(header=_Header("t1"), journal=_journal(path))
    repository.append(_Record("root", None, "one"))
    repository.append(_Record("left", "root", "two"))
    repository.select_leaf("root")
    repository.append(_Record("right", "root", "three"))

    assert repository.leaf_id == "right"
    assert repository.path_to() == (
        _Record("root", None, "one"),
        _Record("right", "root", "three"),
    )
    assert repository.children("root") == (
        _Record("left", "root", "two"),
        _Record("right", "root", "three"),
    )

    loaded = TranscriptRepository.load(
        _journal(path),
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
    )

    assert loaded.header == _Header("t1")
    assert loaded.records == repository.records
    assert loaded.leaf_id == "right"


def test_transcript_repository_forks_selected_path_without_source_mutation(
    tmp_path: Path,
) -> None:
    source = _repository(
        header=_Header("source"),
        records=(
            _Record("root", None, "one"),
            _Record("left", "root", "two"),
            _Record("right", "root", "three"),
        ),
    )

    forked = source.fork(
        header=_Header("fork"),
        journal=_journal(tmp_path / "fork.jsonl"),
        leaf_id="left",
    )

    assert forked.header == _Header("fork")
    assert forked.records == (
        _Record("root", None, "one"),
        _Record("left", "root", "two"),
    )
    assert forked.leaf_id == "left"
    assert source.records[-1].record_id == "right"


def test_transcript_repository_does_not_mutate_memory_when_append_fails() -> None:
    class _FailingJournal:
        path = Path("never-written.jsonl")

        def rewrite(self, records, *, header=None):
            del records, header

        def append(self, record):
            del record
            raise OSError("disk full")

    import pytest

    repository = _repository(
        header=_Header("t1"),
        records=(_Record("root", None, "one"),),
        journal=_FailingJournal(),
    )

    with pytest.raises(OSError, match="disk full"):
        repository.append(_Record("next", "root", "two"))

    assert repository.records == (_Record("root", None, "one"),)
    assert repository.leaf_id == "root"


def test_transcript_repository_detached_load_does_not_write_source(
    tmp_path: Path,
) -> None:
    from loushang.harness.journal import TranscriptRepository

    path = tmp_path / "transcript.jsonl"
    source = _repository(header=_Header("t1"), journal=_journal(path))
    source.append(_Record("root", None, "one"))
    original_bytes = path.read_bytes()

    detached = TranscriptRepository.load(
        _journal(path),
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        writable=False,
    )
    detached.append(_Record("local", "root", "two"))

    assert detached.leaf_id == "local"
    assert path.read_bytes() == original_bytes
