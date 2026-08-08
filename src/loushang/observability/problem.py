"""Compatibility forwarding surface for observability problem records."""

from loushang.foundation.json import JSONPrimitive, JSONValue
from loushang.foundation.observability.problem import (
    ProblemRecord,
    ProblemSeverity,
    ensure_json_safe_mapping,
    ensure_json_safe_value,
)

__all__ = [
    "JSONPrimitive",
    "JSONValue",
    "ProblemRecord",
    "ProblemSeverity",
    "ensure_json_safe_mapping",
    "ensure_json_safe_value",
]
