from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest


def _header(conversation_id: str):
    from loushang.harness.conversation import ConversationHeader

    return ConversationHeader(
        conversation_id=conversation_id,
        version=1,
        created_at="2026-07-13T00:00:00Z",
    )


def _record(
    record_id: str,
    parent_id: str | None,
    payload: str,
    *,
    kind: str = "message",
):
    from loushang.harness.conversation import ConversationRecord

    return ConversationRecord(
        record_id=record_id,
        parent_id=parent_id,
        kind=kind,
        payload_version=1,
        created_at="2026-07-13T00:00:00Z",
        payload=payload,
    )


def _journal(path: Path):
    from loushang.harness.conversation import (
        ConversationHeader,
        ConversationRecord,
        FunctionalConversationHeaderCodec,
        FunctionalConversationRecordCodec,
    )
    from loushang.harness.journal import JournalLoadPolicy, JsonlJournal

    return JsonlJournal(
        path,
        header_codec=FunctionalConversationHeaderCodec[ConversationHeader](
            encoder=lambda header: {
                "type": "conversation",
                "version": header.version,
                "id": header.conversation_id,
                "createdAt": header.created_at,
                "parentId": header.parent_conversation_id,
                "metadata": dict(header.metadata),
            },
            decoder=lambda value: ConversationHeader(
                conversation_id=str(value["id"]),
                version=int(value["version"]),
                created_at=str(value["createdAt"]),
                parent_conversation_id=(
                    str(value["parentId"])
                    if value.get("parentId") is not None
                    else None
                ),
                metadata=dict(value.get("metadata", {})),
            ),
        ),
        record_codec=FunctionalConversationRecordCodec[ConversationRecord[str]](
            encoder=lambda record: {
                "type": "record",
                "id": record.record_id,
                "parentId": record.parent_id,
                "kind": record.kind,
                "payloadVersion": record.payload_version,
                "createdAt": record.created_at,
                "payload": record.payload,
                "metadata": dict(record.metadata),
            },
            decoder=lambda value: ConversationRecord(
                record_id=str(value["id"]),
                parent_id=(
                    str(value["parentId"])
                    if value.get("parentId") is not None
                    else None
                ),
                kind=str(value["kind"]),
                payload_version=int(value["payloadVersion"]),
                created_at=str(value["createdAt"]),
                payload=str(value["payload"]),
                metadata=dict(value.get("metadata", {})),
            ),
        ),
        load_policy=JournalLoadPolicy(header="required"),
    )


def _repository(*, header=None, records=(), journal=None):
    from loushang.harness.conversation import ConversationRepository

    return ConversationRepository.create(
        header=header or _header("conversation-1"),
        records=records,
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        journal=journal,
    )


def test_conversation_repository_persists_branches_builds_tree_and_folds(
    tmp_path: Path,
) -> None:
    from loushang.harness.conversation import (
        ConversationRepository,
        FunctionalConversationFolder,
    )

    path = tmp_path / "conversation.jsonl"
    repository = _repository(journal=_journal(path))
    repository.append(_record("root", None, "one"))
    repository.append(_record("left", "root", "two"))
    repository.branch("root")
    repository.append(_record("right", "root", "three"))

    tree = repository.tree()
    assert len(tree) == 1
    assert tree[0].record.record_id == "root"
    assert [node.record.record_id for node in tree[0].children] == ["left", "right"]
    assert [record.record_id for record in repository.children("root")] == [
        "left",
        "right",
    ]

    folder = FunctionalConversationFolder(
        initial_state=list,
        reducer=lambda state, record: [*state, record.payload],
    )
    assert repository.fold_active(folder) == ["one", "three"]
    assert repository.fold_all(folder) == ["one", "two", "three"]

    loaded = ConversationRepository.load(
        _journal(path),
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
    )
    assert loaded.records == repository.records
    assert loaded.leaf_id == "right"

    read_only = ConversationRepository.load(
        _journal(path),
        record_id=lambda record: record.record_id,
        parent_id=lambda record: record.parent_id,
        writable=False,
    )
    assert read_only.path == path
    with pytest.raises(RuntimeError, match="read-only"):
        read_only.append(_record("blocked", "right", "blocked"))


def test_conversation_repository_forks_only_the_selected_branch() -> None:
    repository = _repository(
        records=(
            _record("root", None, "one"),
            _record("left", "root", "two"),
            _record("right", "root", "three"),
        )
    )

    forked = repository.fork(
        header=_header("forked"),
        journal=None,
        leaf_id="left",
    )

    assert forked.header.conversation_id == "forked"
    assert [record.record_id for record in forked.records] == ["root", "left"]
    assert forked.leaf_id == "left"
    assert [record.record_id for record in repository.records] == [
        "root",
        "left",
        "right",
    ]


def test_conversation_repository_builds_deep_tree_without_recursion() -> None:
    depth = 1_500
    records = tuple(
        _record(
            str(index),
            str(index - 1) if index else None,
            str(index),
        )
        for index in range(depth)
    )
    repository = _repository(records=records)

    tree = repository.tree()

    assert len(tree) == 1
    node = tree[0]
    visited = 1
    while node.children:
        assert len(node.children) == 1
        node = node.children[0]
        visited += 1
    assert visited == depth
    assert node.record.record_id == str(depth - 1)


@dataclass(frozen=True)
class _Projection:
    conversation_id: str
    text: str
    message_count: int


def _projection_index(path: Path):
    from loushang.harness.journal import (
        FunctionalProjectionCodec,
        JsonProjectionIndex,
    )

    return JsonProjectionIndex(
        path,
        version=1,
        items_key="conversations",
        codec=FunctionalProjectionCodec(
            encoder=lambda projection: {
                "id": projection.conversation_id,
                "text": projection.text,
                "messageCount": projection.message_count,
            },
            decoder=lambda value: _Projection(
                conversation_id=str(value["id"]),
                text=str(value["text"]),
                message_count=int(value["messageCount"]),
            ),
        ),
        sort_key=lambda projection: projection.message_count,
        reverse=True,
        generated_at=lambda: "2026-07-13T00:00:00Z",
    )


def test_conversation_catalog_projects_indexes_and_queries(tmp_path: Path) -> None:
    from loushang.harness.conversation import (
        ConversationCatalog,
        FunctionalConversationProjector,
        ProjectionQuery,
    )

    discovered = [
        _repository(
            header=_header("short"),
            records=(_record("s1", None, "alpha"),),
        ),
        _repository(
            header=_header("long"),
            records=(
                _record("l1", None, "alpha"),
                _record("l2", "l1", "beta"),
            ),
        ),
        _repository(
            header=_header("other"),
            records=(_record("o1", None, "gamma"),),
        ),
    ]
    discovery_calls = 0

    def discover():
        nonlocal discovery_calls
        discovery_calls += 1
        return tuple(discovered)

    projector = FunctionalConversationProjector(
        lambda header, records, leaf_id, source_path: _Projection(
            conversation_id=header.conversation_id,
            text=" ".join(record.payload for record in records),
            message_count=len(records),
        )
    )
    catalog = ConversationCatalog(
        discover=discover,
        projector=projector,
        index=_projection_index(tmp_path / "catalog.json"),
    )

    assert [item.conversation_id for item in catalog.refresh()] == [
        "long",
        "short",
        "other",
    ]
    assert discovery_calls == 1
    assert [item.conversation_id for item in catalog.list()] == [
        "long",
        "short",
        "other",
    ]
    assert discovery_calls == 1

    matches = catalog.query(
        ProjectionQuery(
            predicate=lambda item: "alpha" in item.text,
            sort_key=lambda item: item.conversation_id,
            limit=1,
        )
    )
    assert [item.conversation_id for item in matches] == ["long"]

    discovered.pop()
    assert len(catalog.list()) == 3
    assert len(catalog.list(refresh=True)) == 2
    assert discovery_calls == 2


def test_conversation_catalog_projection_failure_policy_is_explicit() -> None:
    from loushang.harness.conversation import (
        ConversationCatalog,
        FunctionalConversationProjector,
    )

    discovered = (
        _repository(header=_header("good"), records=()),
        _repository(header=_header("bad"), records=()),
    )

    def project(header, records, leaf_id, source_path):
        del records, leaf_id, source_path
        if header.conversation_id == "bad":
            raise ValueError("bad projection")
        return header.conversation_id

    projector = FunctionalConversationProjector(project)
    with pytest.raises(ValueError, match="bad projection"):
        ConversationCatalog(
            discover=lambda: discovered,
            projector=projector,
        ).scan()

    errors: list[tuple[str, str]] = []
    compatible = ConversationCatalog(
        discover=lambda: discovered,
        projector=projector,
        skip_projection_errors=True,
        on_projection_error=lambda repository, error: errors.append(
            (repository.header.conversation_id, str(error))
        ),
    )

    assert compatible.scan() == ("good",)
    assert errors == [("bad", "bad projection")]


def test_conversation_contracts_reject_invalid_identity_and_query_limits() -> None:
    from loushang.harness.conversation import (
        CommandExecutionRecord,
        ConversationHeader,
        ProjectionQuery,
    )

    with pytest.raises(ValueError, match="conversation id"):
        ConversationHeader(conversation_id=" ", version=1, created_at="now")
    with pytest.raises(ValueError, match="positive"):
        ConversationHeader(conversation_id="id", version=0, created_at="now")
    with pytest.raises(TypeError, match="command"):
        CommandExecutionRecord(command=1, output="", exit_code=None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exit code"):
        CommandExecutionRecord(command="true", output="", exit_code=True)
    with pytest.raises(TypeError, match="cancelled"):
        CommandExecutionRecord(
            command="true",
            output="",
            exit_code=0,
            cancelled=1,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="non-negative"):
        ProjectionQuery(limit=-1)
    with pytest.raises(TypeError, match="integer"):
        ProjectionQuery(limit=True)
    with pytest.raises(TypeError, match="boolean"):
        ProjectionQuery(reverse=1)  # type: ignore[arg-type]

    metadata = {"cwd": "/workspace", "nested": {"tags": ["original"]}}
    record = CommandExecutionRecord(
        command="",
        output="clean",
        exit_code=0,
        metadata=metadata,
    )
    metadata["nested"]["tags"].append("source-mutated")
    assert record.cancelled is False
    assert record.metadata == {
        "cwd": "/workspace",
        "nested": {"tags": ["original"]},
    }
    with pytest.raises(TypeError):
        record.metadata["cwd"] = "/other"  # type: ignore[index]

    nested = record.metadata["nested"]
    assert isinstance(nested, dict)
    nested["tags"].append("mutated")
    assert record.metadata["nested"] == {"tags": ["original"]}

    payload = asdict(record)
    assert type(payload["metadata"]) is dict
    assert json.loads(json.dumps(payload))["metadata"] == payload["metadata"]
