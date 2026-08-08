from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Literal, TypeAlias

from ..json import JSONValue

ProblemSeverity: TypeAlias = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ProblemRecord:
    code: str
    severity: ProblemSeverity = "error"
    source: str | None = None
    message: str = ""
    recoverable: bool = False
    details: dict[str, JSONValue] = field(default_factory=dict)
    exception_type: str | None = None
    exception_message: str | None = None
    time: str = ""
    monotonic_ms: int = 0
    module: str | None = None
    component: str | None = None
    session_id: str | None = None
    run_id: int | str | None = None
    cwd: str | None = None
    mode: str | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        return asdict(self)


def ensure_json_safe_mapping(
    value: Mapping[str, object] | None,
    *,
    name: str = "details",
) -> dict[str, JSONValue]:
    if value is None:
        return {}

    result: dict[str, JSONValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{name} must be JSON-safe: keys must be strings")
        result[key] = ensure_json_safe_value(item, name=f"{name}.{key}")
    return result


def ensure_json_safe_value(value: object, *, name: str = "value") -> JSONValue:
    if value is None or isinstance(value, str | bool | int):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{name} must be JSON-safe: non-finite float")
        return value

    if isinstance(value, list | tuple):
        return [ensure_json_safe_value(item, name=f"{name}[]") for item in value]

    if isinstance(value, Mapping):
        return ensure_json_safe_mapping(value, name=name)

    raise TypeError(f"{name} must be JSON-safe: got {type(value).__name__}")
