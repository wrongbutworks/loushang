from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from inspect import Parameter, signature
from types import NoneType
from typing import (
    Annotated,
    Any,
    NotRequired,
    Required,
    TypedDict,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

_SCALAR_TYPES: dict[type[object], str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _base_object_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }


def _unwrap_annotation(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _unwrap_annotation(get_args(annotation)[0])
    if origin in (Required, NotRequired):
        return _unwrap_annotation(get_args(annotation)[0])
    if origin is None and annotation is not None:
        return annotation
    return annotation


def _merge_schema(base: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = dict(base)
    for key, value in overrides.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_schema(merged[key], value)
        else:
            merged[key] = value
    return merged


def apply_schema_overrides(schema: dict[str, object], overrides: dict[str, object] | None) -> dict[str, object]:
    if overrides in (None, {}):
        return schema
    if not isinstance(overrides, dict):
        raise TypeError("schema overrides must be a mapping")
    return _merge_schema(schema, overrides)


def infer_schema_from_signature(fn: object, *, exclude_names: set[str] | frozenset[str] | None = None) -> dict[str, object]:
    sig = signature(fn)
    hints = get_type_hints(fn, include_extras=True)
    schema = _base_object_schema()
    properties = schema["properties"]
    required = schema["required"]
    excluded = set(exclude_names or ())

    for param in sig.parameters.values():
        if param.name in excluded:
            continue
        if param.kind == Parameter.POSITIONAL_ONLY:
            raise TypeError("positional-only parameters are not supported for schema inference")
        if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
            raise TypeError("variadic parameters are not supported for schema inference")
        if param.name not in hints:
            raise TypeError(f"parameter {param.name!r} must be annotated")
        annotation = hints[param.name]
        properties[param.name] = infer_schema_from_type(annotation)
        if param.default is Parameter.empty:
            required.append(param.name)

    return schema


def infer_schema_from_type(annotation: object) -> dict[str, object]:
    annotation = _unwrap_annotation(annotation)

    if annotation is Any:
        raise TypeError("cannot infer schema from typing.Any")

    origin = get_origin(annotation)
    if origin is None:
        if annotation in _SCALAR_TYPES:
            return {"type": _SCALAR_TYPES[annotation]}

        if isinstance(annotation, type):
            if is_typeddict(annotation):
                return _infer_schema_from_typeddict(annotation)
            if is_dataclass(annotation):
                return _infer_schema_from_dataclass(annotation)
            if _is_pydantic_model(annotation):
                return _infer_schema_from_pydantic_model(annotation)

        raise TypeError(f"unsupported schema annotation: {annotation!r}")

    if origin is list:
        (item_annotation,) = get_args(annotation) or (Any,)
        return {"type": "array", "items": infer_schema_from_type(item_annotation)}

    if origin is tuple:
        args = get_args(annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": infer_schema_from_type(args[0])}
        raise TypeError("fixed-length tuples are not supported for schema inference")

    union_args = get_args(annotation)
    if union_args and any(arg is NoneType for arg in union_args):
        non_none = [arg for arg in union_args if arg is not NoneType]
        if len(non_none) != 1:
            raise TypeError("optional unions must contain exactly one non-None type")
        return {
            "anyOf": [
                infer_schema_from_type(non_none[0]),
                {"type": "null"},
            ]
        }

    if origin is NoneType or annotation is NoneType:
        raise TypeError("bare None is not a supported schema annotation")

    raise TypeError(f"unsupported schema annotation: {annotation!r}")


def _infer_schema_from_dataclass(cls: type[object]) -> dict[str, object]:
    type_hints = get_type_hints(cls, include_extras=True)
    schema = _base_object_schema()
    properties = schema["properties"]
    required = schema["required"]

    for field in fields(cls):
        annotation = type_hints.get(field.name, field.type)
        properties[field.name] = infer_schema_from_type(annotation)
        if field.default is MISSING and field.default_factory is MISSING:
            required.append(field.name)

    return schema


def _infer_schema_from_typeddict(cls: type[TypedDict]) -> dict[str, object]:
    type_hints = get_type_hints(cls, include_extras=True)
    schema = _base_object_schema()
    properties = schema["properties"]
    required = schema["required"]

    required_keys = getattr(cls, "__required_keys__", frozenset())
    optional_keys = getattr(cls, "__optional_keys__", frozenset())

    for name, annotation in type_hints.items():
        properties[name] = infer_schema_from_type(annotation)
        if name in required_keys:
            required.append(name)
        elif name not in optional_keys and getattr(cls, "__total__", True):
            required.append(name)

    return schema


def _is_pydantic_model(annotation: type[object]) -> bool:
    try:
        from pydantic import BaseModel
    except ImportError:
        return False
    return issubclass(annotation, BaseModel)


def _infer_schema_from_pydantic_model(annotation: type[object]) -> dict[str, object]:
    if hasattr(annotation, "model_json_schema"):
        schema = annotation.model_json_schema()
    elif hasattr(annotation, "schema"):
        schema = annotation.schema()
    else:
        raise TypeError("pydantic model does not expose a schema method")

    if not isinstance(schema, dict):
        raise TypeError("pydantic model schema must be a mapping")
    _raise_on_unresolved_pydantic_refs(schema)
    return schema


def _raise_on_unresolved_pydantic_refs(value: object, *, in_properties_map: bool = False) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not in_properties_map and key in {"$ref", "$defs", "definitions"}:
                raise ValueError("unresolved pydantic refs are not yet supported")
            if key == "properties":
                _raise_on_unresolved_pydantic_refs(item, in_properties_map=True)
            else:
                _raise_on_unresolved_pydantic_refs(item)
    elif isinstance(value, list):
        for item in value:
            _raise_on_unresolved_pydantic_refs(item)
