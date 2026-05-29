from __future__ import annotations

from loushang.ai.utils.json_parse import parse_streaming_json


def test_parse_streaming_json_repairs_tool_arguments_with_raw_controls_and_bad_escape() -> None:
    raw = '{"path":"tmp/bmi.html","content":"line 1\tline 2\nbad escape: \\H"}'

    assert parse_streaming_json(raw) == {
        "path": "tmp/bmi.html",
        "content": "line 1\tline 2\nbad escape: \\H",
    }


def test_parse_streaming_json_repairs_partial_object() -> None:
    raw = '{"path":"tmp/bmi.html","content":"unfinished'

    assert parse_streaming_json(raw) == {
        "path": "tmp/bmi.html",
        "content": "unfinished",
    }
