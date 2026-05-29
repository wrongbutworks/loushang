from __future__ import annotations

from typing import Any

from loushang.coding.message.json_codec import serialize_json_value


def serialize_context_usage_payload(value: object | None) -> dict[str, Any] | None:
    if value is None:
        return None

    raw = serialize_json_value(value)
    if not isinstance(raw, dict):
        return {"value": raw}
    return _camelize(raw)


def _camelize(value: object) -> object:
    if isinstance(value, dict):
        return {_snake_to_camel(str(key)): _camelize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    if len(parts) == 1:
        return value
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
