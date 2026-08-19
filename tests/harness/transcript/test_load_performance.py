"""Load-path performance regression for large Conversation JSONL transcripts.

Resuming a 19 MB coding session used to take ~17s because every record
payload was deep-validated three to four times with eager error-path string
construction, and every Model Input integrity check re-serialized each
primitive through a throwaway JSON document.  These tests pin the single-pass
behavior: a large journal must load well inside one second per megabyte, and
the detailed (copying) validator must never run for valid input.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import loushang.foundation.json as foundation_json
from loushang.harness.conversation.jsonl_codec import (
    ConversationJsonlHeaderCodec,
    ConversationJsonlRecordCodec,
)
from loushang.harness.conversation.types import ConversationHeader, ConversationRecord
from loushang.harness.journal import JournalLoadPolicy, load_jsonl
from loushang.harness.transcript.codecs import (
    create_agent_transcript_payload_registry,
)
from loushang.harness.transcript.kinds import MODEL_INPUT_COMPONENT_KIND
from loushang.harness.transcript.model_input_v2_types import (
    MODEL_INPUT_V2_PAYLOAD_VERSION,
    ModelInputNodeBundle,
    ModelInputNodeReference,
    create_model_input_json_chunk,
    create_model_input_json_value,
    create_model_input_sequence_tail,
)

_CHUNKS_PER_RECORD = 2
_REFERENCES_PER_RECORD = 60
_RECORD_COUNT = 280
_CHUNK_TEXT = "性能回归测试数据 chunk with mixed 中文 content 1234567890. " * 48


def _structured_value(index: int) -> dict[str, object]:
    """A messages-shaped value with thousands of primitives per record."""

    return {
        "messages": [
            {
                "role": "user" if ordinal % 2 == 0 else "assistant",
                "content": f"消息内容 {index}:{ordinal} " * 20,
                "metadata": {
                    "turn": ordinal,
                    "tokens": ordinal * 37,
                    "ratio": ordinal / 3.0,
                    "flags": [True, False, None],
                    "tags": [f"tag-{tag}" for tag in range(12)],
                },
            }
            for ordinal in range(24)
        ],
        "tools": [
            {"name": f"tool_{tool}", "arity": tool, "cost": tool * 1.5}
            for tool in range(15)
        ],
    }


def _write_large_journal(path: Path) -> int:
    registry = create_agent_transcript_payload_registry()
    header_codec = ConversationJsonlHeaderCodec()
    record_codec = ConversationJsonlRecordCodec(registry)
    header = ConversationHeader(
        conversation_id="perf-session",
        version=1,
        created_at="2026-08-19T00:00:00Z",
        parent_conversation_id=None,
        metadata={},
    )
    lines = [
        json.dumps(
            header_codec.encode_header(header),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    ]
    for index in range(_RECORD_COUNT):
        chunks = tuple(
            create_model_input_json_chunk(f"{_CHUNK_TEXT}{index}:{ordinal}")
            for ordinal in range(_CHUNKS_PER_RECORD)
        )
        value_node = create_model_input_json_value(_structured_value(index))
        item_node = create_model_input_json_value({"item": index, "ok": True})
        references = tuple(
            ModelInputNodeReference(
                record_id=f"record-{index}",
                ordinal=_CHUNKS_PER_RECORD + 2,
                node_kind="json_value",
                content_hash=item_node.content_hash,
            )
            for _ in range(_REFERENCES_PER_RECORD)
        )
        bundle = ModelInputNodeBundle(
            nodes=(
                value_node,
                *chunks,
                item_node,
                create_model_input_sequence_tail(
                    previous_tail=None,
                    appended_items=references,
                    total_item_count=_REFERENCES_PER_RECORD,
                    sequence_hash=references[0].content_hash,
                ),
            )
        )
        record = ConversationRecord(
            record_id=f"record-{index}",
            parent_id=None if index == 0 else f"record-{index - 1}",
            kind=MODEL_INPUT_COMPONENT_KIND,
            payload_version=MODEL_INPUT_V2_PAYLOAD_VERSION,
            created_at="2026-08-19T00:00:00Z",
            payload=bundle,
            metadata={},
        )
        lines.append(
            json.dumps(
                record_codec.encode_record(record),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path.stat().st_size


def test_large_conversation_journal_loads_within_budget(tmp_path: Path) -> None:
    journal_path = tmp_path / "large.jsonl"
    size = _write_large_journal(journal_path)
    assert size > 8 * 1024 * 1024  # the fixture must stay meaningfully large

    registry = create_agent_transcript_payload_registry()
    record_codec = ConversationJsonlRecordCodec(registry)

    started = time.monotonic()
    snapshot = load_jsonl(
        journal_path,
        record_codec=record_codec,
        header_codec=ConversationJsonlHeaderCodec(),
        load_policy=JournalLoadPolicy(header="required"),
    )
    elapsed = time.monotonic() - started

    assert len(snapshot.records) == _RECORD_COUNT
    megabytes = size / (1024 * 1024)
    # Historical behavior: ~0.9s/MB.  Current: ~0.25s/MB.  The budget keeps a
    # 2x margin over current hardware while failing the old implementation.
    assert elapsed < 0.5 * megabytes, (
        f"loaded {megabytes:.1f} MB in {elapsed:.2f}s "
        f"({elapsed / megabytes:.2f}s/MB); expected < 0.5s/MB"
    )


def test_valid_journal_avoids_the_detailed_validator_on_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    journal_path = tmp_path / "large.jsonl"
    _write_large_journal(journal_path)
    registry = create_agent_transcript_payload_registry()
    record_codec = ConversationJsonlRecordCodec(registry)

    calls = 0
    original = foundation_json._require_json_value

    def _counting(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(foundation_json, "_require_json_value", _counting)
    snapshot = load_jsonl(
        journal_path,
        record_codec=record_codec,
        header_codec=ConversationJsonlHeaderCodec(),
        load_policy=JournalLoadPolicy(header="required"),
    )
    assert len(snapshot.records) == _RECORD_COUNT
    # Only the small per-record metadata mappings may still use the detailed
    # copying validator; payload trees must go through the fast single-pass
    # validation.  The old implementation made hundreds of thousands of calls
    # here (several per payload node).
    assert calls <= 2 * (_RECORD_COUNT + 1), (
        f"detailed validator ran {calls} times for {_RECORD_COUNT} records"
    )
