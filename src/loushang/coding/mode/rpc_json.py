from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from pathlib import Path

from loushang.protocol import JSONValue, require_json_value


class RpcJsonProjectionError(TypeError):
    def __init__(self, message: str, *, path: str, value_type: str) -> None:
        super().__init__(message)
        self.path = path
        self.value_type = value_type


def project_rpc_value(value: object, *, name: str = "rpc_output") -> JSONValue:
    """Project Coding RPC values through its documented transport policy."""

    return require_json_value(
        _project_rpc_value(value, path=name, seen=set()),
        name=name,
    )


def _project_rpc_value(
    value: object,
    *,
    path: str,
    seen: set[int],
) -> JSONValue:
    if value is None:
        return None
    if type(value) is str:
        return str(value)
    if type(value) is bool:
        return bool(value)
    if type(value) is int:
        return int(value)
    if type(value) is float:
        value = float(value)
        if not math.isfinite(value):
            raise _projection_error(value, path, "non-finite floats are not JSON")
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _project_container(
            value,
            path=path,
            seen=seen,
            project=lambda: {
                field.name: _project_rpc_value(
                    getattr(value, field.name),
                    path=f"{path}.{field.name}",
                    seen=seen,
                )
                for field in fields(value)
            },
        )
    if isinstance(value, Mapping):
        return _project_container(
            value,
            path=path,
            seen=seen,
            project=lambda: _project_mapping(value, path=path, seen=seen),
        )
    if isinstance(value, list | tuple):
        return _project_container(
            value,
            path=path,
            seen=seen,
            project=lambda: [
                _project_rpc_value(
                    item,
                    path=f"{path}[{index}]",
                    seen=seen,
                )
                for index, item in enumerate(value)
            ],
        )
    raise _projection_error(value, path, "unsupported RPC value")


def _project_mapping(
    value: Mapping[object, object],
    *,
    path: str,
    seen: set[int],
) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise _projection_error(key, path, "RPC object keys must be strings")
        key = str(key)
        child_path = f"{path}.{key}" if key else f"{path}['']"
        result[key] = _project_rpc_value(item, path=child_path, seen=seen)
    return result


def _project_container(
    value: object,
    *,
    path: str,
    seen: set[int],
    project: Callable[[], JSONValue],
) -> JSONValue:
    object_id = id(value)
    if object_id in seen:
        raise _projection_error(value, path, "circular reference")
    seen.add(object_id)
    try:
        return project()
    finally:
        seen.remove(object_id)


def _projection_error(
    value: object,
    path: str,
    reason: str,
) -> RpcJsonProjectionError:
    value_type = type(value).__name__
    return RpcJsonProjectionError(
        f"{path} cannot be projected to RPC JSON: {reason} ({value_type})",
        path=path,
        value_type=value_type,
    )


__all__ = ["RpcJsonProjectionError", "project_rpc_value"]
