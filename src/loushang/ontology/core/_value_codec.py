"""Strict JSON envelope for values persisted by ontology stores."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from loushang.foundation.json import JSONValue, require_json_mapping, require_json_value


def encode_store_value(value: object) -> dict[str, JSONValue]:
    if isinstance(value, datetime):
        return {"kind": "datetime", "value": value.isoformat()}
    return {"kind": "json", "value": require_json_value(value, name="ontology value")}


def decode_store_value(value: object) -> Any:
    envelope = require_json_mapping(value, name="stored ontology value")
    kind = envelope.get("kind")
    encoded = envelope.get("value")
    if kind == "datetime" and isinstance(encoded, str):
        return datetime.fromisoformat(encoded)
    if kind == "json":
        return encoded
    raise ValueError("Invalid stored ontology value envelope")


def encoded_mapping(value: dict[str, Any]) -> dict[str, JSONValue]:
    return cast(
        dict[str, JSONValue],
        {name: encode_store_value(item) for name, item in value.items()},
    )


__all__ = ["decode_store_value", "encode_store_value", "encoded_mapping"]
