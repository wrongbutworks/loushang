from __future__ import annotations

import pytest

from loushang.ai.tool.validation import (
    validate_tool_arguments,
    validate_tool_arguments_result,
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
