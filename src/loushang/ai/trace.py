from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loushang.observability import get_log
from loushang.observability.problem import JSONValue

_log = get_log(__name__).bind(component="AITrace")
_REDACTED = "<redacted>"
_SENSITIVE_KEYS = {
    "apikey",
    "authorization",
    "bearertoken",
    "clientsecret",
    "idtoken",
    "password",
    "refreshtoken",
    "secret",
    "xapikey",
}


def emit_trace(options: Any | None, event: dict) -> None:
    _emit_options_trace(options, event)
    _emit_observability_trace(event)


def _emit_options_trace(options: Any | None, event: dict) -> None:
    if options is None:
        return
    handler = getattr(options, "trace", None)
    if callable(handler):
        try:
            handler(event)
        except Exception:
            pass


def _emit_observability_trace(event: dict) -> None:
    try:
        _log.debug_event(
            "provider",
            _event_name(event),
            event=_summarize_event(event),
        )
    except Exception:
        pass


def _event_name(event: Mapping[str, object]) -> str:
    raw_type = event.get("type")
    if isinstance(raw_type, str) and raw_type:
        return raw_type.replace(":", ".")
    return "event"


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
        return {str(item_key): _json_safe(item, key=str(item_key)) for item_key, item in value.items()}
    return str(value)


def _summarize_event(event: Mapping[str, object]) -> JSONValue:
    return {str(key): _summarize_event_value(str(key), value) for key, value in event.items()}


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
