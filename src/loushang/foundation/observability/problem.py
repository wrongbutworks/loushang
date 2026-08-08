"""Compatibility aliases for pre-split problem imports."""

from ..json import JSONValue
from .projection import ensure_json_safe_mapping, ensure_json_safe_value
from .records import ProblemRecord, ProblemSeverity

__all__ = [
    "JSONValue",
    "ProblemRecord",
    "ProblemSeverity",
    "ensure_json_safe_mapping",
    "ensure_json_safe_value",
]
