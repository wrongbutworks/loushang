from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.harnesstui.commands.interaction import (
    CommandInteractionPresentationCopy,
    CommandInteractionSnapshot,
    CommandPaletteChooser,
    present_command_interaction,
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


async def coding_command_completion_provider(
    session: Any,
    *,
    command_catalog: CodingCommandCatalog | None = None,
) -> CompletionProvider:
    return command_completion_provider(
        await _catalog_commands(session, command_catalog=command_catalog)
    )


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
    return present_command_interaction(result, copy=_COMMAND_INTERACTION_COPY)


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


def _command_value(item: object) -> str:
    completion = command_completion_item(item)
    return completion.value if completion is not None else ""


_COMMAND_INTERACTION_COPY = CommandInteractionPresentationCopy[object](
    list_items=format_commands,
    item_text=_command_value,
    cancelled="Command selection cancelled.",
    empty="No commands available.",
    no_match=lambda query: f"No commands match: {query}",
    ambiguous_title="Multiple commands match:",
    ambiguous_hint="Use /command <full command> to select one.",
    selected_prefix="Command selected: ",
)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "CommandPaletteChooser",
    "coding_command_completion_provider",
    "coding_command_palette",
    "format_coding_commands",
    "select_coding_command",
]
