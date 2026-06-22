from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loushang.observability import get_log
from loushang.observability.problem import JSONValue

_log = get_log(__name__).bind(component="AITrace")
TRACE_SCHEMA = "loushang.ai.trace.v1"
_REDACTED = "<redacted>"
_SENSITIVE_KEYS = {
    "accesstoken",
    "apikey",
    "apitoken",
    "authorization",
    "bearertoken",
    "clientsecret",
    "idtoken",
    "password",
    "refreshtoken",
    "secret",
    "xapikey",
}


TraceEvent = dict[str, JSONValue]


def emit_trace(options: Any | None, event: Mapping[str, object]) -> None:
    normalized = normalize_trace_event(event)
    _emit_options_trace(options, normalized)
    _emit_observability_trace(normalized)


def normalize_trace_event(event: Mapping[str, object]) -> TraceEvent:
    event_type = _trace_type(event)
    source, name = _trace_source_name(event_type)
    data = {
        str(key): _summarize_event_value(str(key), value)
        for key, value in event.items()
        if key != "type"
    }
    return {
        "schema": TRACE_SCHEMA,
        "type": event_type,
        "source": source,
        "name": name,
        "data": data,
    }


def _emit_options_trace(options: Any | None, event: TraceEvent) -> None:
    if options is None:
        return
    handler = getattr(options, "trace", None)
    if callable(handler):
        try:
            handler(event)
        except Exception:
            pass


def _emit_observability_trace(event: TraceEvent) -> None:
    try:
        _log.debug_event(
            "provider",
            _event_name(event),
            event=event,
        )
    except Exception:
        pass


def _event_name(event: Mapping[str, object]) -> str:
    raw_type = event.get("type")
    if isinstance(raw_type, str) and raw_type:
        return raw_type.replace(":", ".")
    return "event"


def _trace_type(event: Mapping[str, object]) -> str:
    raw_type = event.get("type")
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    return "event"


def _trace_source_name(event_type: str) -> tuple[str, str]:
    if ":" in event_type:
        source, name = event_type.split(":", 1)
        return source or "event", name or "event"
    return "event", event_type


def _json_safe(value: object, *, key: str | None = None) -> JSONValue:
    if key is not None and _is_sensitive_key(key):
        return _REDACTED
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(item_key): _json_safe(item, key=str(item_key))
            for item_key, item in value.items()
        }
    return str(value)


def _summarize_event_value(key: str, value: object) -> JSONValue:
    if _is_sensitive_key(key):
        return _REDACTED
    if key == "args" and isinstance(value, Mapping):
        return _summarize_tool_args(value)
    return _json_safe(value, key=key)


def _summarize_tool_args(args: Mapping[str, object]) -> dict[str, JSONValue]:
    keys: list[JSONValue] = [str(key) for key in sorted(args, key=str)]
    summary: dict[str, JSONValue] = {
        "kind": "object",
        "keys": keys,
    }
    path = args.get("path")
    if isinstance(path, str):
        summary["path"] = path
    content = args.get("content")
    if isinstance(content, str):
        summary["content_chars"] = len(content)
    command = args.get("command")
    if isinstance(command, str):
        summary["command_chars"] = len(command)
    return summary


def _is_sensitive_key(key: str) -> bool:
    compacted = "".join(char for char in key.lower() if char.isalnum())
    return compacted in _SENSITIVE_KEYS


__all__ = ["TRACE_SCHEMA", "TraceEvent", "emit_trace", "normalize_trace_event"]
