from __future__ import annotations

from typing import Any, cast

from loushang.harness.presentation import ToolDefinitionResolver
from loushang.harnesstui.conversation.runtime_view import (
    StringQueueReader,
    StringQueueSource,
    stable_string_queue_reader,
)
from loushang.tui.keybindings import KeybindingConfig


def tool_definition_resolver(session: Any) -> ToolDefinitionResolver | None:
    getter = getattr(session, "get_tool_definition", None)
    return cast(ToolDefinitionResolver, getter) if callable(getter) else None


def _session_queue_source(
    session: Any,
    method_name: str,
) -> StringQueueSource | None:
    source = getattr(session, method_name, None)
    return cast(StringQueueSource, source) if callable(source) else None


def pending_steers_reader(session: Any) -> StringQueueReader:
    return stable_string_queue_reader(
        _session_queue_source(session, "get_steering_messages")
    )


def pending_followups_reader(session: Any) -> StringQueueReader:
    return stable_string_queue_reader(
        _session_queue_source(session, "get_follow_up_messages")
    )


def session_keybindings(session: Any) -> KeybindingConfig | None:
    settings_manager = getattr(session, "settings_manager", None)
    if settings_manager is None:
        return None
    get_keybindings = getattr(settings_manager, "get_keybindings", None)
    if callable(get_keybindings):
        return cast(KeybindingConfig | None, get_keybindings())
    get_settings = getattr(settings_manager, "get_settings", None)
    if callable(get_settings):
        return cast(
            KeybindingConfig | None,
            getattr(get_settings(), "keybindings", None),
        )
    return None


__all__ = [
    "pending_followups_reader",
    "pending_steers_reader",
    "session_keybindings",
    "tool_definition_resolver",
]
