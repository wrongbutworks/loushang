from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.harnesstui.commands.interaction import (
    CommandInteractionResult,
    CommandInteractionSnapshot,
    CommandPaletteChooser,
    run_command_interaction,
)
from loushang.harnesstui.commands.presentation import (
    command_completion_item,
    command_completion_provider,
    format_commands,
)
from loushang.tui import (
    CommandPalette,
    CompletionProvider,
)
from loushang.tui import (
    CompletionItem as CompletionItem,
)


async def format_session_commands(session: Any, *, query: str = "") -> str:
    return format_commands(await _session_command_items(session), query=query)


async def format_coding_commands(
    session: Any,
    *,
    query: str = "",
    command_catalog: CodingCommandCatalog | None = None,
) -> str:
    return format_commands(
        await _catalog_commands(session, command_catalog=command_catalog),
        query=query,
    )


async def session_command_completion_provider(session: Any) -> CompletionProvider:
    return command_completion_provider(
        await _session_command_items(session),
        local_last=False,
    )


async def coding_command_completion_provider(
    session: Any,
    *,
    command_catalog: CodingCommandCatalog | None = None,
) -> CompletionProvider:
    return command_completion_provider(
        await _catalog_commands(session, command_catalog=command_catalog)
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
        session,
        command_catalog=command_catalog,
    )
    return CommandPalette.from_completion_provider(provider, title=title)


async def select_session_command(
    session: Any,
    *,
    query: str = "",
    choose: CommandPaletteChooser | None = None,
) -> str:
    items = await _session_command_items(session)
    result = await run_command_interaction(
        CommandInteractionSnapshot(items, local_last=False),
        query=query,
        choose=choose,
    )
    return _format_command_interaction(result)


async def select_coding_command(
    session: Any,
    *,
    query: str = "",
    choose: CommandPaletteChooser | None = None,
    command_catalog: CodingCommandCatalog | None = None,
) -> str:
    items = await _catalog_commands(session, command_catalog=command_catalog)
    result = await run_command_interaction(
        CommandInteractionSnapshot(items),
        query=query,
        choose=choose,
    )
    return _format_command_interaction(result)


async def _catalog_commands(
    session: Any,
    *,
    command_catalog: CodingCommandCatalog | None = None,
) -> tuple[object, ...]:
    if command_catalog is not None:
        return tuple(command_catalog.commands())
    session_commands = await _session_command_items(session)
    catalog = CodingCommandCatalog(
        session_commands=lambda: session_commands,
    )
    return catalog.commands()


async def _session_command_items(session: Any) -> tuple[object, ...]:
    getter = getattr(session, "list_commands", None)
    if not callable(getter):
        return ()
    raw_commands = await _maybe_await(getter())
    if not isinstance(raw_commands, Iterable):
        return ()
    return tuple(raw_commands)


def _format_command_interaction(result: CommandInteractionResult[object]) -> str:
    if result.kind == "list":
        return format_commands(result.matches)
    if result.kind == "cancelled":
        return "Command selection cancelled."
    if result.kind == "empty":
        if result.query:
            return f"No commands match: {result.query}"
        return "No commands available."
    if result.kind == "ambiguous":
        return "\n".join(
            [
                "Multiple commands match:",
                *(f"  {_command_value(item)}" for item in result.matches),
                "Use /command <full command> to select one.",
            ]
        )
    if result.item is not None:
        return f"Command selected: {_command_value(result.item)}"
    return "No commands available."


def _command_value(item: object) -> str:
    completion = command_completion_item(item)
    return completion.value if completion is not None else ""


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
