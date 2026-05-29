from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from loushang.tui import CommandPalette, CompletionItem, CompletionProvider

CommandPaletteChooser = Callable[[CommandPalette], Awaitable[str | None] | str | None]


async def format_session_commands(session: Any, *, query: str = "") -> str:
    getter = getattr(session, "list_commands", None)
    if not callable(getter):
        return "No commands available."

    raw_commands = await _maybe_await(getter())
    if not isinstance(raw_commands, Iterable):
        return "No commands available."

    lines = [_format_command(command) for command in raw_commands]
    lines = [line for line in lines if line]
    stripped_query = query.strip()
    if stripped_query:
        needle = stripped_query.lower()
        lines = [line for line in lines if needle in line.lower()]

    if not lines:
        if stripped_query:
            return f"No commands match: {stripped_query}"
        return "No commands available."

    return "\n".join(["Commands:", *sorted(lines)])


async def session_command_completion_provider(session: Any) -> CompletionProvider:
    getter = getattr(session, "list_commands", None)
    if not callable(getter):
        return CompletionProvider(())

    raw_commands = await _maybe_await(getter())
    if not isinstance(raw_commands, Iterable):
        return CompletionProvider(())

    items = sorted(
        (item for command in raw_commands if (item := _command_completion_item(command)) is not None),
        key=lambda item: item.value,
    )
    return CompletionProvider(tuple(items))


async def session_command_palette(session: Any, *, title: str = "Commands") -> CommandPalette:
    provider = await session_command_completion_provider(session)
    return CommandPalette.from_completion_provider(provider, title=title)


async def select_session_command(
    session: Any,
    *,
    query: str = "",
    choose: CommandPaletteChooser | None = None,
) -> str:
    stripped_query = query.strip()
    if not stripped_query:
        if choose is not None:
            selected = await _maybe_await(choose(await session_command_palette(session, title="Commands")))
            if selected is None:
                return "Command selection cancelled."
            return await select_session_command(session, query=selected)
        return await format_session_commands(session)

    provider = await session_command_completion_provider(session)
    matches = _matching_command_items(provider, stripped_query)
    if not matches:
        return f"No commands match: {stripped_query}"
    if len(matches) != 1:
        return "\n".join(
            [
                "Multiple commands match:",
                *(f"  {item.value}" for item in matches),
                "Use /command <full command> to select one.",
            ]
        )

    return f"Command selected: {matches[0].value}"


def _format_command(command: object) -> str:
    name = _string_attr(command, "invocation_name") or _string_attr(command, "name")
    if name is None:
        return ""
    label = _command_label(name, _string_attr(command, "argument_hint"))
    description = _string_attr(command, "description")
    source = _string_attr(command, "source")
    if description:
        label = f"{label} - {description}"
    if source:
        label = f"{label} ({source})"
    return label


def _command_completion_item(command: object) -> CompletionItem | None:
    name = _string_attr(command, "invocation_name") or _string_attr(command, "name")
    if name is None:
        return None
    argument_hint = _string_attr(command, "argument_hint")
    description = _string_attr(command, "description") or ""
    source = _string_attr(command, "source")
    if source:
        description = f"{description} ({source})" if description else f"({source})"
    value = f"/{name}"
    return CompletionItem(value=value, label=_command_label(name, argument_hint), description=description)


def _command_label(name: str, argument_hint: str | None) -> str:
    if argument_hint:
        return f"/{name} {argument_hint}"
    return f"/{name}"


def _matching_command_items(provider: CompletionProvider, query: str) -> tuple[CompletionItem, ...]:
    needle = query.lower()
    matches = tuple(item for item in provider.items if _command_item_matches(item, needle))
    exact = tuple(
        item
        for item in matches
        if item.value.lower() == needle or item.display_label().lower() == needle
    )
    return exact or matches


def _command_item_matches(item: CompletionItem, needle: str) -> bool:
    haystacks = (item.value, item.display_label(), item.description)
    for haystack in haystacks:
        lowered = haystack.lower()
        if needle in lowered:
            return True
        if not needle.startswith("/") and needle in lowered.removeprefix("/"):
            return True
    return False


def _string_attr(value: object, name: str) -> str | None:
    raw = getattr(value, name, None)
    return raw if isinstance(raw, str) and raw else None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "CommandPaletteChooser",
    "format_session_commands",
    "select_session_command",
    "session_command_completion_provider",
    "session_command_palette",
]
