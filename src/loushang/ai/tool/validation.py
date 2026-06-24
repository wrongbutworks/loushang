from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from loushang.ai.types import Tool, ToolCall

ToolValidationPolicy = Literal["strict", "coerce"]
ToolValidationDiagnosticCode = Literal["tool_argument_coerced"]


@dataclass(frozen=True)
class ToolValidationDiagnostic:
    code: ToolValidationDiagnosticCode
    path: str
    message: str
    from_type: str
    to_type: str
    level: Literal["info", "warning"] = "warning"


@dataclass(frozen=True)
class ToolValidationResult:
    arguments: dict[str, Any]
    diagnostics: tuple[ToolValidationDiagnostic, ...] = ()


@dataclass(frozen=True)
class _SchemaIssue:
    path: str
    message: str


def validate_tool_call(
    tools: list[Tool],
    tool_call: ToolCall,
    *,
    validation_policy: ToolValidationPolicy = "strict",
) -> dict[str, Any]:
    return validate_tool_call_result(
        tools,
        tool_call,
        validation_policy=validation_policy,
    ).arguments


def validate_tool_call_result(
    tools: list[Tool],
    tool_call: ToolCall,
    *,
    validation_policy: ToolValidationPolicy = "strict",
) -> ToolValidationResult:
    for tool in tools:
        if tool.name == tool_call.name:
            return validate_tool_arguments_result(
                tool,
                tool_call,
                validation_policy=validation_policy,
            )
    raise ValueError(f"Unknown tool call: {tool_call.name!r}")


def validate_tool_arguments(
    tool: Tool,
    tool_call: ToolCall,
    *,
    validation_policy: ToolValidationPolicy = "strict",
) -> dict[str, Any]:
    return validate_tool_arguments_result(
        tool,
        tool_call,
        validation_policy=validation_policy,
    ).arguments


def validate_tool_arguments_result(
    tool: Tool,
    tool_call: ToolCall,
    *,
    validation_policy: ToolValidationPolicy = "strict",
) -> ToolValidationResult:
    if tool.name != tool_call.name:
        raise ValueError(
            f"Tool name mismatch: tool={tool.name!r} tool_call={tool_call.name!r}"
        )
    if validation_policy not in {"strict", "coerce"}:
        raise ValueError(f"Unsupported tool validation policy: {validation_policy!r}")
    arguments = deepcopy(tool_call.arguments)
    diagnostics: list[ToolValidationDiagnostic] = []
    if validation_policy == "coerce":
        arguments = _coerce_schema(
            arguments,
            tool.parameters,
            path="$",
            diagnostics=diagnostics,
        )
    issues = _collect_schema_issues(arguments, tool.parameters, path="$")
    if issues:
        raise ValueError(_format_validation_error(tool, tool_call, issues))
    return ToolValidationResult(arguments=arguments, diagnostics=tuple(diagnostics))


def _validate_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    issues = _collect_schema_issues(value, schema, path=path)
    if issues:
        issue = issues[0]
        raise ValueError(f"{issue.path} {issue.message}")


def _collect_schema_issues(
    value: Any, schema: dict[str, Any], *, path: str
) -> list[_SchemaIssue]:
    # Composite keywords
    if "oneOf" in schema:
        subs = schema.get("oneOf") or []
        matches = 0
        for sub in subs:
            if isinstance(sub, dict) and not _collect_schema_issues(
                value, sub, path=path
            ):
                matches += 1
        if matches != 1:
            return [_SchemaIssue(path, "must match exactly one schema in oneOf")]
        return []
    if "anyOf" in schema:
        subs = schema.get("anyOf") or []
        for sub in subs:
            if isinstance(sub, dict) and not _collect_schema_issues(
                value, sub, path=path
            ):
                return []
        return [_SchemaIssue(path, "must match at least one schema in anyOf")]
    if "allOf" in schema:
        issues: list[_SchemaIssue] = []
        subs = schema.get("allOf") or []
        for sub in subs:
            if isinstance(sub, dict):
                issues.extend(_collect_schema_issues(value, sub, path=path))
        return issues

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        for item_type in schema_type:
            if isinstance(item_type, str) and not _collect_schema_issues(
                value, {**schema, "type": item_type}, path=path
            ):
                return []
        return [_SchemaIssue(path, f"must match one of {schema_type!r}")]

    if schema_type == "object":
        if not isinstance(value, dict):
            return [_SchemaIssue(path, "must be an object")]
        issues = []
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                issues.append(_SchemaIssue(f"{path}.{key}", "is required"))
        properties = schema.get("properties", {})
        additional_properties = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                issues.extend(
                    _collect_schema_issues(item, properties[key], path=f"{path}.{key}")
                )
            elif additional_properties is False:
                issues.append(_SchemaIssue(f"{path}.{key}", "is not allowed"))
            elif isinstance(additional_properties, dict):
                issues.extend(
                    _collect_schema_issues(
                        item, additional_properties, path=f"{path}.{key}"
                    )
                )
        return issues

    if schema_type == "array":
        if not isinstance(value, list):
            return [_SchemaIssue(path, "must be an array")]
        issues = []
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            issues.append(
                _SchemaIssue(path, f"must contain at least {min_items} items")
            )
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            issues.append(_SchemaIssue(path, f"must contain at most {max_items} items"))
        prefix_items = schema.get("prefixItems")
        if isinstance(prefix_items, list):
            for index, item_schema in enumerate(prefix_items):
                if index < len(value) and isinstance(item_schema, dict):
                    issues.extend(
                        _collect_schema_issues(
                            value[index], item_schema, path=f"{path}[{index}]"
                        )
                    )
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                issues.extend(
                    _collect_schema_issues(item, item_schema, path=f"{path}[{index}]")
                )
        return issues

    if schema_type == "string":
        if not isinstance(value, str):
            return [_SchemaIssue(path, "must be a string")]
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            return [_SchemaIssue(path, f"must have minLength {min_length}")]
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            return [_SchemaIssue(path, f"must have maxLength {max_length}")]
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            return [_SchemaIssue(path, f"must match pattern {pattern!r}")]
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            return [_SchemaIssue(path, f"must be one of {enum!r}")]
        return []

    if schema_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return [_SchemaIssue(path, "must be an integer")]
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            return [_SchemaIssue(path, f"must be one of {enum!r}")]
        return []

    if schema_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            return [_SchemaIssue(path, "must be a number")]
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            return [_SchemaIssue(path, f"must be one of {enum!r}")]
        return []

    if schema_type == "boolean":
        if not isinstance(value, bool):
            return [_SchemaIssue(path, "must be a boolean")]
        return []

    if schema_type in {None, "null"}:
        if schema_type == "null" and value is not None:
            return [_SchemaIssue(path, "must be null")]
        return []
    return []


def _coerce_schema(
    value: Any,
    schema: dict[str, Any],
    *,
    path: str,
    diagnostics: list[ToolValidationDiagnostic],
) -> Any:
    next_value = value

    for sub in schema.get("allOf") or []:
        if isinstance(sub, dict):
            next_value = _coerce_schema(
                next_value,
                sub,
                path=path,
                diagnostics=diagnostics,
            )

    for keyword in ("anyOf", "oneOf"):
        subs = schema.get(keyword)
        if isinstance(subs, list):
            for sub in subs:
                if not isinstance(sub, dict):
                    continue
                candidate_diagnostics: list[ToolValidationDiagnostic] = []
                candidate = _coerce_schema(
                    deepcopy(next_value),
                    sub,
                    path=path,
                    diagnostics=candidate_diagnostics,
                )
                if not _collect_schema_issues(candidate, sub, path=path):
                    next_value = candidate
                    diagnostics.extend(candidate_diagnostics)
                    break

    schema_types = _schema_types(schema)
    matches_union_member = len(schema_types) > 1 and any(
        _matches_json_type(next_value, schema_type) for schema_type in schema_types
    )
    if schema_types and not matches_union_member:
        for schema_type in schema_types:
            candidate = _coerce_primitive_by_type(next_value, schema_type)
            if _value_changed(next_value, candidate):
                diagnostics.append(
                    _coercion_diagnostic(
                        path=path,
                        value=next_value,
                        schema_type=schema_type,
                    )
                )
                next_value = candidate
                break

    if "object" in schema_types and isinstance(next_value, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, property_schema in properties.items():
                if key in next_value and isinstance(property_schema, dict):
                    next_value[key] = _coerce_schema(
                        next_value[key],
                        property_schema,
                        path=f"{path}.{key}",
                        diagnostics=diagnostics,
                    )
        additional_properties = schema.get("additionalProperties")
        if isinstance(additional_properties, dict):
            for key in set(next_value) - set(properties or {}):
                next_value[key] = _coerce_schema(
                    next_value[key],
                    additional_properties,
                    path=f"{path}.{key}",
                    diagnostics=diagnostics,
                )

    if "array" in schema_types and isinstance(next_value, list):
        prefix_items = schema.get("prefixItems")
        if isinstance(prefix_items, list):
            for index, item_schema in enumerate(prefix_items):
                if index < len(next_value) and isinstance(item_schema, dict):
                    next_value[index] = _coerce_schema(
                        next_value[index],
                        item_schema,
                        path=f"{path}[{index}]",
                        diagnostics=diagnostics,
                    )
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(next_value):
                next_value[index] = _coerce_schema(
                    item,
                    item_schema,
                    path=f"{path}[{index}]",
                    diagnostics=diagnostics,
                )

    return next_value


def _schema_types(schema: dict[str, Any]) -> list[str]:
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        return [schema_type]
    if isinstance(schema_type, list):
        return [item for item in schema_type if isinstance(item, str)]
    return []


def _matches_json_type(value: Any, schema_type: str) -> bool:
    if schema_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "null":
        return value is None
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "object":
        return isinstance(value, dict)
    return False


def _coerce_primitive_by_type(value: Any, schema_type: str) -> Any:
    if schema_type == "number":
        if value is None:
            return 0
        if isinstance(value, str) and value.strip():
            try:
                parsed = float(value)
            except ValueError:
                return value
            return parsed if math.isfinite(parsed) else value
        if isinstance(value, bool):
            return 1 if value else 0
        return value
    if schema_type == "integer":
        if value is None:
            return 0
        if isinstance(value, str) and value.strip():
            try:
                parsed = float(value)
            except ValueError:
                return value
            if parsed.is_integer():
                return int(parsed)
        if isinstance(value, bool):
            return 1 if value else 0
        return value
    if schema_type == "boolean":
        if value is None:
            return False
        if isinstance(value, str):
            if value == "true":
                return True
            if value == "false":
                return False
        if isinstance(value, int | float) and not isinstance(value, bool):
            if value == 1:
                return True
            if value == 0:
                return False
        return value
    if schema_type == "string":
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        return value
    if schema_type == "null":
        if value in {"", 0, False}:
            return None
        return value
    return value


def _value_changed(previous: Any, current: Any) -> bool:
    if current is previous:
        return False
    return current != previous or type(current) is not type(previous)


def _coercion_diagnostic(
    *,
    path: str,
    value: Any,
    schema_type: str,
) -> ToolValidationDiagnostic:
    from_type = _json_type_name(value)
    return ToolValidationDiagnostic(
        code="tool_argument_coerced",
        path=path,
        message=f"Coerced tool argument from {from_type} to {schema_type}.",
        from_type=from_type,
        to_type=schema_type,
        level="warning",
    )


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _format_validation_error(
    tool: Tool, tool_call: ToolCall, issues: list[_SchemaIssue]
) -> str:
    errors = (
        "\n".join(
            f"  - {_format_validation_path(issue.path)}: {issue.message}"
            for issue in issues
        )
        or "Unknown validation error"
    )
    return (
        f'Validation failed for tool "{tool.name}":\n'
        f"{errors}\n\n"
        "Received arguments:\n"
        f"{json.dumps(tool_call.arguments, indent=2, ensure_ascii=False)}"
    )


def _format_validation_path(path: str) -> str:
    if path == "$":
        return "root"
    if path.startswith("$."):
        return path[2:]
    if path.startswith("$"):
        return path[1:] or "root"
    return path or "root"
