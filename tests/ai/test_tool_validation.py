from __future__ import annotations

import pytest

from loushang.ai.tool import validation as _validation
from loushang.ai.tool.validation import (
    validate_tool_arguments,
    validate_tool_arguments_result,
    validate_tool_call,
    validate_tool_call_result,
)
from loushang.ai.types import Tool, ToolCall


def _probe_tool() -> Tool:
    return Tool(
        name="probe",
        description="probe",
        parameters={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "label": {"type": "string"},
            },
            "required": ["count", "enabled", "label"],
            "additionalProperties": False,
        },
    )


def test_validate_tool_arguments_defaults_to_strict_without_mutating_input() -> None:
    tool = _probe_tool()
    tool_call = ToolCall(
        type="toolCall",
        id="tc_1",
        name="probe",
        arguments={"count": 42, "enabled": True, "label": "ready"},
    )

    validated = validate_tool_arguments(tool, tool_call)

    assert validated == {"count": 42, "enabled": True, "label": "ready"}
    assert validated is not tool_call.arguments
    assert tool_call.arguments == {"count": 42, "enabled": True, "label": "ready"}


def test_validate_tool_arguments_strict_rejects_implicit_conversion() -> None:
    tool = _probe_tool()
    tool_call = ToolCall(
        type="toolCall",
        id="tc_1",
        name="probe",
        arguments={"count": "42", "enabled": "true", "label": 123},
    )

    with pytest.raises(ValueError) as exc_info:
        validate_tool_arguments(tool, tool_call)

    message = str(exc_info.value)
    assert "  - count: must be an integer" in message
    assert "  - enabled: must be a boolean" in message
    assert "  - label: must be a string" in message
    assert tool_call.arguments == {"count": "42", "enabled": "true", "label": 123}


def test_validate_tool_arguments_coerce_policy_reports_diagnostics() -> None:
    tool = _probe_tool()
    tool_call = ToolCall(
        type="toolCall",
        id="tc_1",
        name="probe",
        arguments={"count": "42", "enabled": "true", "label": 123},
    )

    result = validate_tool_arguments_result(
        tool,
        tool_call,
        validation_policy="coerce",
    )

    assert result.arguments == {"count": 42, "enabled": True, "label": "123"}
    assert [
        (diagnostic.code, diagnostic.path, diagnostic.from_type, diagnostic.to_type)
        for diagnostic in result.diagnostics
    ] == [
        ("tool_argument_coerced", "$.count", "string", "integer"),
        ("tool_argument_coerced", "$.enabled", "string", "boolean"),
        ("tool_argument_coerced", "$.label", "integer", "string"),
    ]
    assert (
        validate_tool_arguments(
            tool,
            tool_call,
            validation_policy="coerce",
        )
        == result.arguments
    )
    assert tool_call.arguments == {"count": "42", "enabled": "true", "label": 123}


def test_validate_tool_call_result_uses_selected_policy() -> None:
    tool = Tool(
        name="probe",
        description="probe",
        parameters={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "label": {"type": "string"},
            },
            "required": ["count", "enabled", "label"],
            "additionalProperties": False,
        },
    )
    tool_call = ToolCall(
        type="toolCall",
        id="tc_1",
        name="probe",
        arguments={"count": "42", "enabled": "true", "label": 123},
    )

    result = validate_tool_call_result(
        [Tool(name="other", description="other", parameters={}), tool],
        tool_call,
        validation_policy="coerce",
    )

    assert result.arguments == {"count": 42, "enabled": True, "label": "123"}
    assert len(result.diagnostics) == 3


def test_validate_tool_call_wrapper_and_error_paths() -> None:
    tool = _probe_tool()
    tool_call = ToolCall(
        type="toolCall",
        id="tc_1",
        name="probe",
        arguments={"count": 1, "enabled": False, "label": "ready"},
    )

    assert validate_tool_call([tool], tool_call) == {
        "count": 1,
        "enabled": False,
        "label": "ready",
    }

    with pytest.raises(ValueError, match="Unknown tool call"):
        validate_tool_call_result(
            [Tool(name="other", description="other", parameters={})],
            tool_call,
        )
    with pytest.raises(ValueError, match="Tool name mismatch"):
        validate_tool_arguments(
            Tool(name="other", description="other", parameters={}),
            tool_call,
        )
    with pytest.raises(ValueError, match="Unsupported tool validation policy"):
        validate_tool_arguments_result(
            tool,
            tool_call,
            validation_policy="loose",  # type: ignore[arg-type]
        )


def test_validate_tool_arguments_coerce_policy_supports_bool_and_null_compat() -> None:
    tool = Tool(
        name="probe",
        description="probe",
        parameters={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "ratio": {"type": "number"},
                "enabled": {"type": "boolean"},
                "label": {"type": "string"},
                "empty": {"type": "null"},
            },
            "required": ["count", "ratio", "enabled", "label", "empty"],
            "additionalProperties": False,
        },
    )
    tool_call = ToolCall(
        type="toolCall",
        id="tc_1",
        name="probe",
        arguments={
            "count": False,
            "ratio": True,
            "enabled": 1,
            "label": None,
            "empty": "",
        },
    )

    result = validate_tool_arguments_result(
        tool,
        tool_call,
        validation_policy="coerce",
    )

    assert result.arguments == {
        "count": 0,
        "ratio": 1,
        "enabled": True,
        "label": "",
        "empty": None,
    }
    assert [
        (diagnostic.path, diagnostic.from_type, diagnostic.to_type)
        for diagnostic in result.diagnostics
    ] == [
        ("$.count", "boolean", "integer"),
        ("$.ratio", "boolean", "number"),
        ("$.enabled", "integer", "boolean"),
        ("$.label", "null", "string"),
        ("$.empty", "string", "null"),
    ]


def test_validate_tool_arguments_coerces_nested_composites_and_arrays() -> None:
    tool = Tool(
        name="probe",
        description="probe",
        parameters={
            "allOf": [
                {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "choice": {
                            "anyOf": [
                                {"type": "integer"},
                                {"type": "boolean"},
                            ]
                        },
                        "exact": {
                            "oneOf": [
                                {"type": "integer"},
                                {"type": "boolean"},
                            ]
                        },
                        "tuple": {
                            "type": "array",
                            "prefixItems": [
                                {"type": "integer"},
                                {"type": "boolean"},
                            ],
                        },
                        "numbers": {
                            "type": "array",
                            "items": {"type": "number"},
                        },
                    },
                    "additionalProperties": {"type": "integer"},
                }
            ]
        },
    )
    tool_call = ToolCall(
        type="toolCall",
        id="tc_1",
        name="probe",
        arguments={
            "count": "7",
            "choice": "8",
            "exact": "9",
            "tuple": ["1", "false"],
            "numbers": ["2.5", True],
            "extra": "10",
        },
    )

    result = validate_tool_arguments_result(
        tool,
        tool_call,
        validation_policy="coerce",
    )

    assert result.arguments == {
        "count": 7,
        "choice": 8,
        "exact": 9,
        "tuple": [1, False],
        "numbers": [2.5, 1],
        "extra": 10,
    }
    assert {
        (diagnostic.path, diagnostic.from_type, diagnostic.to_type)
        for diagnostic in result.diagnostics
    } >= {
        ("$.choice", "string", "integer"),
        ("$.exact", "string", "integer"),
        ("$.tuple[0]", "string", "integer"),
        ("$.tuple[1]", "string", "boolean"),
        ("$.numbers[0]", "string", "number"),
        ("$.numbers[1]", "boolean", "number"),
        ("$.extra", "string", "integer"),
    }


def test_validate_schema_accepts_supported_compositions_and_types() -> None:
    _validation._validate_schema(
        "ready",
        {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        path="$",
    )
    _validation._validate_schema(
        42,
        {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        path="$",
    )
    _validation._validate_schema(
        "abc",
        {
            "allOf": [
                {"type": "string", "minLength": 3},
                {"type": "string", "maxLength": 3},
            ]
        },
        path="$",
    )
    _validation._validate_schema(None, {"type": "null"}, path="$")
    _validation._validate_schema(True, {"type": "boolean"}, path="$")
    _validation._validate_schema(
        [1, "x", 2],
        {
            "type": "array",
            "prefixItems": [{"type": "integer"}, {"type": "string"}],
            "items": {"type": ["integer", "string"]},
            "minItems": 2,
            "maxItems": 3,
        },
        path="$",
    )


@pytest.mark.parametrize(
    ("value", "schema", "message"),
    [
        ("x", {"oneOf": [{"type": "string"}, {"enum": ["x"]}]}, "oneOf"),
        ([], {"anyOf": [{"type": "string"}, {"type": "integer"}]}, "anyOf"),
        ({"name": "a"}, {"type": "object", "required": ["count"]}, "is required"),
        (
            {"extra": "bad"},
            {"type": "object", "additionalProperties": {"type": "integer"}},
            "extra must be an integer",
        ),
        ("not-object", {"type": "object"}, "must be an object"),
        ("not-array", {"type": "array"}, "must be an array"),
        ([], {"type": "array", "minItems": 1}, "at least 1"),
        ([1, 2], {"type": "array", "maxItems": 1}, "at most 1"),
        (["x"], {"type": "array", "prefixItems": [{"type": "integer"}]}, "must be an integer"),
        ("x", {"type": "string", "minLength": 2}, "minLength 2"),
        ("xxx", {"type": "string", "maxLength": 2}, "maxLength 2"),
        ("abc", {"type": "string", "pattern": r"[0-9]+"}, "pattern"),
        ("c", {"type": "string", "enum": ["a", "b"]}, "one of"),
        (3, {"type": "integer", "enum": [1, 2]}, "one of"),
        (3.5, {"type": "number", "enum": [1.5, 2.5]}, "one of"),
        ("x", {"type": "null"}, "must be null"),
        ("x", {"type": ["integer", "boolean"]}, "must match one of"),
    ],
)
def test_validate_schema_reports_constraint_failures(
    value: object, schema: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _validation._validate_schema(value, schema, path="$")


def test_validate_tool_arguments_reports_validation_errors() -> None:
    tool = Tool(
        name="probe",
        description="probe",
        parameters={
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
            "additionalProperties": False,
        },
    )
    tool_call = ToolCall(
        type="toolCall",
        id="tc_1",
        name="probe",
        arguments={"count": "42.5", "extra": True},
    )

    with pytest.raises(ValueError) as exc_info:
        validate_tool_arguments(tool, tool_call)

    message = str(exc_info.value)
    assert 'Validation failed for tool "probe":' in message
    assert "  - count: must be an integer" in message
    assert "  - extra: is not allowed" in message
    assert '"count": "42.5"' in message
