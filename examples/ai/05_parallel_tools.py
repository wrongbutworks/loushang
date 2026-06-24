"""Offline parallel tool-call summary example."""

from __future__ import annotations

import json

from loushang.ai import ToolCall


def _offline_tool_calls() -> list[ToolCall]:
    return [
        ToolCall(
            type="toolCall",
            id="call_add",
            name="add",
            arguments={"a": 2},
        ),
        ToolCall(
            type="toolCall",
            id="call_mul",
            name="multiply",
            arguments={"x": 3},
        ),
    ]


def inspect_parallel_tools() -> dict[str, object]:
    return {
        "stopReason": "toolUse",
        "toolCalls": [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in _offline_tool_calls()
        ],
    }


def main() -> None:
    print(json.dumps(inspect_parallel_tools(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
