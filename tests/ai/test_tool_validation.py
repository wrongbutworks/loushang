from __future__ import annotations

import pytest

from loushang.ai.tool.validation import validate_tool_arguments
from loushang.ai.types import Tool, ToolCall


def test_validate_tool_arguments_coerces_plain_json_schema_primitives_without_mutating_input() -> None:
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

    validated = validate_tool_arguments(tool, tool_call)

    assert validated == {"count": 42, "enabled": True, "label": "123"}
    assert tool_call.arguments == {"count": "42", "enabled": "true", "label": 123}


def test_validate_tool_arguments_coerces_bool_and_null_like_pi() -> None:
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
        arguments={"count": False, "ratio": True, "enabled": 1, "label": None, "empty": ""},
    )

    assert validate_tool_arguments(tool, tool_call) == {
        "count": 0,
        "ratio": 1,
        "enabled": True,
        "label": "",
        "empty": None,
    }


def test_validate_tool_arguments_reports_pi_style_validation_errors() -> None:
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
