from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.harnesstui.commands.presentation import (
    command_completion_provider,
    format_commands,
    matching_command_items,
)
from loushang.tui import (
    CommandPalette,
    CompletionProvider,
)
from loushang.tui import (
    CompletionItem as CompletionItem,
)

CommandPaletteChooser = Callable[[CommandPalette], Awaitable[str | None] | str | None]


async def format_session_commands(session: Any, *, query: str = "") -> str:
    getter = getattr(session, "list_commands", None)
    if not callable(getter):
        return "No commands available."

    raw_commands = await _maybe_await(getter())
    if not isinstance(raw_commands, Iterable):
        return "No commands available."

    return format_commands(raw_commands, query=query)


async def format_coding_commands(
    session: Any,
    *,
    query: str = "",
    command_catalog: CodingCommandCatalog | None = None,
) -> str:
    return format_commands(
        _catalog_commands(session, command_catalog=command_catalog), query=query
    )


async def session_command_completion_provider(session: Any) -> CompletionProvider:
    getter = getattr(session, "list_commands", None)
    if not callable(getter):
        return CompletionProvider(())

    raw_commands = await _maybe_await(getter())
    if not isinstance(raw_commands, Iterable):
        return CompletionProvider(())

    return command_completion_provider(raw_commands, local_last=False)


async def coding_command_completion_provider(
    session: Any,
    *,
    command_catalog: CodingCommandCatalog | None = None,
) -> CompletionProvider:
    return command_completion_provider(
        _catalog_commands(session, command_catalog=command_catalog)
    )


async def session_command_palette(
    session: Any, *, title: str = "Commands"
) -> CommandPalette:
    provider = await session_command_completion_provider(session)
    return CommandPalette.from_completion_provider(provider, title=title)


async def coding_command_palette(
    session: Any,
    *,
    title: str = "Commands",
    command_catalog: CodingCommandCatalog | None = None,
) -> CommandPalette:
    provider = await coding_command_completion_provider(
        session, command_catalog=command_catalog
    )
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
            selected = await _maybe_await(
                choose(await session_command_palette(session, title="Commands"))
            )
            if selected is None:
                return "Command selection cancelled."
            return await select_session_command(session, query=selected)
        return await format_session_commands(session)

    provider = await session_command_completion_provider(session)
    matches = matching_command_items(provider, stripped_query)
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


async def select_coding_command(
    session: Any,
    *,
    query: str = "",
    choose: CommandPaletteChooser | None = None,
    command_catalog: CodingCommandCatalog | None = None,
) -> str:
    stripped_query = query.strip()
    if not stripped_query:
        if choose is not None:
            selected = await _maybe_await(
                choose(
                    await coding_command_palette(
                        session, title="Commands", command_catalog=command_catalog
                    )
                )
            )
            if selected is None:
                return "Command selection cancelled."
            return await select_coding_command(
                session, query=selected, command_catalog=command_catalog
            )
        return await format_coding_commands(session, command_catalog=command_catalog)

    provider = await coding_command_completion_provider(
        session, command_catalog=command_catalog
    )
    matches = matching_command_items(provider, stripped_query)
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


def _catalog_commands(
    session: Any, *, command_catalog: CodingCommandCatalog | None = None
) -> tuple[object, ...]:
    catalog = command_catalog or CodingCommandCatalog(
        session_commands=_session_commands_provider(session)
    )
    return catalog.commands()


def _session_commands_provider(session: Any):
    getter = getattr(session, "list_commands", None)
    if not callable(getter):
        return None
    return getter


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "CommandPaletteChooser",
    "coding_command_completion_provider",
    "coding_command_palette",
    "format_session_commands",
    "format_coding_commands",
    "select_coding_command",
    "select_session_command",
    "session_command_completion_provider",
    "session_command_palette",
]
