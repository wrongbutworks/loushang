from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from loushang.ai.trace import TRACE_SCHEMA, emit_trace
from loushang.observability import (
    configure_observability,
    log_context,
    reset_observability,
)
from loushang.observability.trace import TraceJSONLSink


def setup_function() -> None:
    reset_observability()


def teardown_function() -> None:
    reset_observability()


def test_emit_trace_emits_versioned_options_callback_event() -> None:
    events: list[dict[str, object]] = []
    event = {"type": "sdk:payload", "model": "kimi-for-coding"}

    emit_trace(SimpleNamespace(trace=events.append), event)

    assert events == [
        {
            "schema": TRACE_SCHEMA,
            "type": "sdk:payload",
            "source": "sdk",
            "name": "payload",
            "data": {"model": "kimi-for-coding"},
        }
    ]


def test_emit_trace_redacts_sensitive_options_callback_fields() -> None:
    events: list[dict[str, object]] = []

    emit_trace(
        SimpleNamespace(trace=events.append),
        {
            "type": "sdk:client",
            "headers": {
                "Authorization": "Bearer secret-token",
                "x-api-key": "secret-key",
                "anthropic-version": "2023-06-01",
            },
            "apiKey": "secret-key",
            "access_token": "secret-token",
            "token": "secret-token",
            "oauth": {"accessToken": "secret-token"},
            "credentials": {"apiKey": "secret-key"},
            "total_tokens": 42,
        },
    )

    payload = json.dumps(events[0], sort_keys=True)
    assert "secret" not in payload
    data = events[0]["data"]
    assert data["headers"] == {
        "Authorization": "<redacted>",
        "x-api-key": "<redacted>",
        "anthropic-version": "2023-06-01",
    }
    assert data["apiKey"] == "<redacted>"
    assert data["access_token"] == "<redacted>"
    assert data["token"] == "<redacted>"
    assert data["oauth"] == "<redacted>"
    assert data["credentials"] == "<redacted>"
    assert data["total_tokens"] == 42


def test_emit_trace_writes_provider_debug_event_to_observability_trace(tmp_path: Path) -> None:
    trace_path = tmp_path / "provider.jsonl"
    configure_observability(
        trace_sink=TraceJSONLSink(trace_path),
        trace_scopes={"provider"},
    )

    with log_context(session_id="s1", run_id=6, cwd="/repo", mode="tui"):
        emit_trace(
            None,
            {
                "type": "sdk:tool_done",
                "id": "tool_1",
                "name": "write",
                "args": {"path": "tmp/bmi.html"},
            },
        )

    record = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["kind"] == "debug_event"
    assert record["scope"] == "provider"
    assert record["name"] == "sdk.tool_done"
    assert record["session_id"] == "s1"
    assert record["run_id"] == 6
    assert record["data"] == {
        "event": {
            "schema": TRACE_SCHEMA,
            "type": "sdk:tool_done",
            "source": "sdk",
            "name": "tool_done",
            "data": {
                "id": "tool_1",
                "name": "write",
                "args": {
                    "kind": "object",
                    "keys": ["path"],
                    "path": "tmp/bmi.html",
                },
            },
        }
    }


def test_emit_trace_summarizes_tool_content_for_observability_trace(tmp_path: Path) -> None:
    trace_path = tmp_path / "provider.jsonl"
    configure_observability(
        trace_sink=TraceJSONLSink(trace_path),
        trace_scopes={"provider"},
    )

    emit_trace(
        None,
        {
            "type": "sdk:tool_done",
            "id": "tool_1",
            "name": "write",
            "args": {"path": "tmp/bmi.html", "content": "<html>secret</html>"},
        },
    )

    record = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["data"]["event"]["data"]["args"] == {
        "kind": "object",
        "keys": ["content", "path"],
        "path": "tmp/bmi.html",
        "content_chars": 19,
    }


def test_emit_trace_redacts_sensitive_observability_fields(tmp_path: Path) -> None:
    trace_path = tmp_path / "provider.jsonl"
    configure_observability(
        trace_sink=TraceJSONLSink(trace_path),
        trace_scopes={"provider"},
    )

    emit_trace(
        None,
        {
            "type": "sdk:client",
            "headers": {
                "Authorization": "Bearer secret-token",
                "x-api-key": "secret-key",
                "anthropic-version": "2023-06-01",
            },
            "apiKey": "secret-key",
            "total_tokens": 42,
        },
    )

    record = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    event = record["data"]["event"]["data"]
    assert event["headers"] == {
        "Authorization": "<redacted>",
        "x-api-key": "<redacted>",
        "anthropic-version": "2023-06-01",
    }
    assert event["apiKey"] == "<redacted>"
    assert event["total_tokens"] == 42


def test_emit_trace_stringifies_non_json_safe_event_values(tmp_path: Path) -> None:
    trace_path = tmp_path / "provider.jsonl"
    configure_observability(
        trace_sink=TraceJSONLSink(trace_path),
        trace_scopes={"provider"},
    )

    emit_trace(None, {"type": "sdk:payload", "path": Path("tmp/bmi.html")})

    record = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["data"]["event"]["data"]["path"] == "tmp/bmi.html"


def test_emit_trace_stringifies_non_finite_floats(tmp_path: Path) -> None:
    trace_path = tmp_path / "provider.jsonl"
    configure_observability(
        trace_sink=TraceJSONLSink(trace_path),
        trace_scopes={"provider"},
    )

    emit_trace(
        None,
        {"type": "sdk:usage", "nan_value": float("nan"), "inf_value": float("inf")},
    )

    raw_text = trace_path.read_text(encoding="utf-8")
    record = json.loads(raw_text)
    assert "NaN" not in raw_text
    assert "Infinity" not in raw_text
    assert record["data"]["event"]["data"]["nan_value"] == "nan"
    assert record["data"]["event"]["data"]["inf_value"] == "inf"
