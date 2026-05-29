from __future__ import annotations

from pathlib import Path

import pytest

from loushang.ai.types import AssistantMessage, TextPart, ToolResultMessage, Usage, UserMessage
from loushang.coding.message import CompactionEntry, SessionHeader, SessionMessageEntry


def test_write_then_load_jsonl_session_file(tmp_path: Path) -> None:
    from loushang.coding.store.file_codec import load_session_file, write_session_file

    header = SessionHeader(
        type="session",
        version=1,
        id="s1",
        timestamp="2026-05-20T09:00:00.000Z",
        cwd="/tmp/project",
        parent_session=None,
    )
    entry = SessionMessageEntry(
        type="message",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:01.000Z",
        message=UserMessage(
            role="user",
            content=[TextPart(type="text", text="hi")],
            timestamp=0.0,
        ),
    )

    path = tmp_path / "session.jsonl"
    write_session_file(path, header, [entry])
    loaded_header, loaded_entries = load_session_file(path)

    assert loaded_header.id == "s1"
    assert len(loaded_entries) == 1
    assert loaded_entries[0].type == "message"


def test_session_file_codec_locks_reads_and_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import fcntl

    import loushang.coding.store.file_codec as codec

    calls: list[int] = []

    def fake_flock(_fd: int, op: int) -> None:
        calls.append(op)

    monkeypatch.setattr(codec.fcntl, "flock", fake_flock)

    header = SessionHeader(
        type="session",
        version=1,
        id="s1",
        timestamp="2026-05-20T09:00:00.000Z",
        cwd="/tmp/project",
        parent_session=None,
    )
    entry = SessionMessageEntry(
        type="message",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:01.000Z",
        message=UserMessage(
            role="user",
            content=[TextPart(type="text", text="hi")],
            timestamp=0.0,
        ),
    )
    path = tmp_path / "session.jsonl"

    codec.write_session_file(path, header, [])
    codec.append_session_entry(path, entry)
    codec.load_session_file(path)

    assert fcntl.LOCK_EX in calls
    assert fcntl.LOCK_SH in calls
    assert calls.count(fcntl.LOCK_UN) == 3


def test_load_session_file_rejects_missing_header(tmp_path: Path) -> None:
    from loushang.coding.store.file_codec import load_session_file

    path = tmp_path / "broken.jsonl"
    path.write_text(
        '{"type":"message","id":"e1","parentId":null,"timestamp":"x","message":{"role":"user","content":[],"timestamp":0.0}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_session_file(path)


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("", "empty_session_file"),
        ("not-json\n", "invalid_session_header_json"),
        (
            '{"type":"message","id":"e1","parentId":null,"timestamp":"x","message":{"role":"user","content":[],"timestamp":0.0}}\n',
            "missing_session_header",
        ),
    ],
)
def test_load_session_file_reports_stable_store_error_codes(tmp_path: Path, content: str, code: str) -> None:
    from loushang.coding.store.file_codec import SessionFileError, load_session_file

    path = tmp_path / "broken.jsonl"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(SessionFileError) as exc_info:
        load_session_file(path)

    assert exc_info.value.code == code
    assert exc_info.value.path == path


def test_session_file_codec_uses_pi_v3_json_keys(tmp_path: Path) -> None:
    from loushang.coding.store.file_codec import write_session_file

    header = SessionHeader(
        type="session",
        version=3,
        id="s1",
        timestamp="2026-05-20T09:00:00.000Z",
        cwd="/tmp/project",
        parent_session="/tmp/parent.jsonl",
    )
    assistant = SessionMessageEntry(
        type="message",
        id="e1",
        parent_id=None,
        timestamp="2026-05-20T09:00:01.000Z",
        message=AssistantMessage(
            role="assistant",
            content=[TextPart(type="text", text="hi", text_signature="sig")],
            api="anthropic-messages",
            provider="anthropic",
            model="claude-sonnet",
            response_id="resp-1",
            usage=Usage(
                input=1,
                output=2,
                cache_read=3,
                cache_write=4,
                total_tokens=5,
                cost={"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0},
            ),
            stop_reason="stop",
            error_message=None,
            timestamp=1.0,
        ),
    )
    tool_result = SessionMessageEntry(
        type="message",
        id="e2",
        parent_id="e1",
        timestamp="2026-05-20T09:00:02.000Z",
        message=ToolResultMessage(
            role="toolResult",
            tool_call_id="call-1",
            tool_name="bash",
            content=[TextPart(type="text", text="ok")],
            is_error=False,
            timestamp=2.0,
        ),
    )

    path = tmp_path / "session.jsonl"
    write_session_file(path, header, [assistant, tool_result])
    lines = path.read_text(encoding="utf-8").splitlines()

    assert '"version": 3' in lines[0]
    assert '"parentSession": "/tmp/parent.jsonl"' in lines[0]
    assert '"responseId": "resp-1"' in lines[1]
    assert '"stopReason": "stop"' in lines[1]
    assert '"textSignature": "sig"' in lines[1]
    assert '"cacheRead": 3' in lines[1]
    assert '"cacheWrite": 4' in lines[1]
    assert '"totalTokens": 5' in lines[1]
    assert '"toolCallId": "call-1"' in lines[2]
    assert '"toolName": "bash"' in lines[2]
    assert '"isError": false' in lines[2]
    assert "response_id" not in lines[1]
    assert "stop_reason" not in lines[1]
    assert "tool_call_id" not in lines[2]
    assert "tool_name" not in lines[2]
    assert "is_error" not in lines[2]


def test_session_file_codec_preserves_compaction_plan_details(tmp_path: Path) -> None:
    from loushang.coding.store.file_codec import load_session_file, write_session_file

    header = SessionHeader(
        type="session",
        version=3,
        id="s1",
        timestamp="2026-05-20T09:00:00.000Z",
        cwd="/tmp/project",
        parent_session=None,
    )
    entry = CompactionEntry(
        type="compaction",
        id="c1",
        parent_id="a1",
        timestamp="2026-05-20T09:00:03.000Z",
        summary="summary",
        first_kept_entry_id="u2",
        tokens_before=195,
        details={
            "compactionPlan": {
                "firstKeptEntryId": "u2",
                "summarizedEntryIds": ["u1", "a1"],
                "turnPrefixEntryIds": [],
                "keptEntryIds": ["u2", "a2"],
                "isSplitTurn": False,
                "tokensBefore": 195,
                "keepRecentTokens": 32768,
            }
        },
    )
    path = tmp_path / "session.jsonl"

    write_session_file(path, header, [entry])
    text = path.read_text(encoding="utf-8")
    _, loaded_entries = load_session_file(path)

    assert '"firstKeptEntryId": "u2"' in text
    assert '"compactionPlan"' in text
    assert loaded_entries == [entry]


def test_load_session_file_accepts_pi_v3_user_string_content(tmp_path: Path) -> None:
    from loushang.coding.store.file_codec import load_session_file

    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"type":"session","version":3,"id":"s1","timestamp":"2026-05-20T09:00:00.000Z","cwd":"/tmp/project"}',
                '{"type":"message","id":"e1","parentId":null,"timestamp":"2026-05-20T09:00:01.000Z","message":{"role":"user","content":"Hello","timestamp":1}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    _, entries = load_session_file(path)

    assert len(entries) == 1
    assert entries[0].message.content == "Hello"  # type: ignore[attr-defined]


def test_load_session_file_skips_invalid_lines(tmp_path: Path) -> None:
    from loushang.coding.store.file_codec import load_session_file

    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"type":"session","version":3,"id":"s1","timestamp":"2026-05-20T09:00:00.000Z","cwd":"/tmp/project"}',
                "{not-json}",
                "{}",
                '{"type":"message","id":"e1","parentId":null,"timestamp":"2026-05-20T09:00:01.000Z","message":{"role":"user","content":[{"type":"text","text":"ok"}],"timestamp":1.0}}',
                '{"type":"message","id":"e2","parentId":"e1","timestamp":"2026-05-20T09:00:02.000Z","message":{"role":"assistant","content":[{"type":"text","text":"reply"}],"provider":"anthropic","model":"claude","api":"anthropic-messages","responseId":"resp","usage":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"totalTokens":0},"stopReason":"stop","timestamp":2.0}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    _, entries = load_session_file(path)

    assert len(entries) == 2
    assert entries[0].id == "e1"
    assert entries[1].id == "e2"
