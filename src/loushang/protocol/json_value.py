"""Compatibility forwarding surface for the strict Foundation JSON contract."""

from loushang.foundation.json import (
    JSONPrimitive,
    JSONValue,
    JsonValueError,
    dump_json_value,
    require_json_mapping,
    require_json_value,
)

__all__ = [
    "JSONPrimitive",
    "JSONValue",
    "JsonValueError",
    "dump_json_value",
    "require_json_mapping",
    "require_json_value",
]
