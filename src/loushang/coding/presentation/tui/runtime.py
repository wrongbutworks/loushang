from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from loushang.harness.presentation import ToolDefinitionResolver
from loushang.tui.keybindings import KeybindingConfig

QueueReader = Callable[[], tuple[str, ...]]


def tool_definition_resolver(session: Any) -> ToolDefinitionResolver | None:
    getter = getattr(session, "getToolDefinition", None)
    if not callable(getter):
        getter = getattr(session, "get_tool_definition", None)
    return cast(ToolDefinitionResolver, getter) if callable(getter) else None


def queue_reader(session: Any, method_name: str) -> QueueReader:
    def read() -> tuple[str, ...]:
        method = getattr(session, method_name, None)
        if not callable(method):
            return ()
        try:
            values = method()
        except Exception:
            return ()
        if not isinstance(values, list | tuple):
            return ()
        return tuple(value for value in values if isinstance(value, str))

    return read


def pending_steers_reader(session: Any) -> QueueReader:
    return queue_reader(session, "get_steering_messages")


def pending_followups_reader(session: Any) -> QueueReader:
    return queue_reader(session, "get_follow_up_messages")


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
    "queue_reader",
    "session_keybindings",
    "tool_definition_resolver",
]
