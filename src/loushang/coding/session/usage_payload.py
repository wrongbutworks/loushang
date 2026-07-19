from __future__ import annotations

from dataclasses import asdict
from typing import Any

from loushang.harness.agent_transcript import ContextUsageSnapshot
from loushang.harness.session.inspection import ContextUsage
from loushang.protocol import JSONValue, require_json_mapping


def serialize_context_usage_payload(value: object | None) -> dict[str, Any] | None:
    if value is None:
        return None

    if isinstance(value, ContextUsage | ContextUsageSnapshot):
        value = asdict(value)
    raw = require_json_mapping(value, name="context_usage")
    return _camelize(raw)


def _camelize(value: JSONValue) -> JSONValue:
    if isinstance(value, dict):
        return {_snake_to_camel(key): _camelize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    if len(parts) == 1:
        return value
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
