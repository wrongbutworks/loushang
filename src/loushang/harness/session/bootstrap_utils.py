"""Small, product-neutral helpers used while constructing Agent sessions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry

NoToolsMode = Literal["all", "builtin"]


def normalize_no_tools(no_tools: NoToolsMode | bool | None) -> NoToolsMode | None:
    if no_tools is True:
        return "all"
    if no_tools in (False, None):
        return None
    if no_tools in {"all", "builtin"}:
        return no_tools
    raise ValueError("no_tools must be 'all', 'builtin', True, False, or None")


def loader_system_prompt_override(resource_loader: object) -> str | None:
    getter = getattr(resource_loader, "get_system_prompt_override", None)
    if not callable(getter):
        return None
    value = getter()
    return value if isinstance(value, str) else None


def loader_append_system_prompt(resource_loader: object) -> list[str]:
    getter = getattr(resource_loader, "get_append_system_prompt_overrides", None)
    if not callable(getter):
        return []
    values = getter()
    if not isinstance(values, list | tuple):
        return []
    return [value for value in values if isinstance(value, str) and value.strip()]


def append_system_prompt_fragments(
    base_prompt: str,
    fragments: Sequence[str],
) -> str:
    parts = (
        [base_prompt.strip()]
        if isinstance(base_prompt, str) and base_prompt.strip()
        else []
    )
    parts.extend(
        fragment.strip()
        for fragment in fragments
        if isinstance(fragment, str) and fragment.strip()
    )
    return "\n\n".join(parts)


def resolve_initial_active_tool_names(
    *,
    active_tool_names: list[str] | None,
    allowed_tool_names: set[str] | None,
    no_tools_mode: NoToolsMode | None,
    tool_registry: WorkspaceToolRegistry | None,
) -> list[str] | None:
    if no_tools_mode == "all":
        return []
    if active_tool_names is not None:
        names = list(active_tool_names)
    elif no_tools_mode == "builtin":
        names = non_builtin_tool_names(tool_registry)
    else:
        return None
    if allowed_tool_names is not None:
        return [name for name in names if name in allowed_tool_names]
    return names


def non_builtin_tool_names(
    tool_registry: WorkspaceToolRegistry | None,
) -> list[str]:
    if tool_registry is None:
        return []
    builtin_names = {"bash", "read", "ls", "find", "grep", "write", "edit"}
    return [
        definition.name
        for definition in tool_registry.list_enabled_definitions()
        if definition.name not in builtin_names
    ]


def split_model_thinking_pattern(pattern: str) -> tuple[str, str | None]:
    name, separator, suffix = pattern.rpartition(":")
    if (
        separator
        and suffix in {"off", "minimal", "low", "medium", "high", "xhigh"}
        and name
    ):
        return name, suffix
    return pattern, None


__all__ = [
    "NoToolsMode",
    "append_system_prompt_fragments",
    "loader_append_system_prompt",
    "loader_system_prompt_override",
    "non_builtin_tool_names",
    "normalize_no_tools",
    "resolve_initial_active_tool_names",
    "split_model_thinking_pattern",
]
