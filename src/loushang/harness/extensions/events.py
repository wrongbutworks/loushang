from __future__ import annotations

VALID_EXTENSION_EVENTS = (
    "session_start",
    "session_before_switch",
    "session_before_fork",
    "session_before_compact",
    "session_before_tree",
    "session_compact",
    "session_tree",
    "session_refresh",
    "before_agent_start",
    "session_shutdown",
    "resources_discover",
    "input",
    "agent_start",
    "agent_end",
    "turn_start",
    "turn_end",
    "message_start",
    "message_update",
    "message_end",
    "tool_execution_start",
    "tool_execution_update",
    "tool_execution_end",
    "user_bash",
    "model_select",
    "context",
    "tool_call",
    "tool_result",
)


__all__ = ["VALID_EXTENSION_EVENTS"]
