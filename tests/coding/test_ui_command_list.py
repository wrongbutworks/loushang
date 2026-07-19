from __future__ import annotations

import asyncio
from types import SimpleNamespace


class _Session:
    def list_commands(self) -> list[object]:
        return [
            SimpleNamespace(
                name="hotkeys",
                description="Show all keyboard shortcuts",
                source="builtin",
            ),
            SimpleNamespace(
                name="deploy",
                invocation_name="deploy:1",
                description="Deploy app",
                source="extension",
            ),
        ]


class _ArgumentHintSession:
    def list_commands(self) -> list[object]:
        return [
            SimpleNamespace(
                name="review",
                description="Review pull request",
                source="prompt",
                argument_hint="<PR-URL>",
            ),
        ]


class _BuiltinSession:
    def list_commands(self) -> list[object]:
        from loushang.coding.session.builtin_commands import (
            list_builtin_command_descriptors,
        )

        return list_builtin_command_descriptors()


class _AsyncSession:
    async def list_commands(self) -> list[object]:
        await asyncio.sleep(0)
        return [
            SimpleNamespace(
                name="inspect",
                description="Inspect asynchronously",
                source="session",
            )
        ]


class _EmptyCatalog:
    def commands(self) -> tuple[object, ...]:
        return ()


def test_format_coding_commands_projects_session_command() -> None:
    from loushang.coding.commands.tui import format_coding_commands

    text = asyncio.run(format_coding_commands(_Session(), query="deploy"))

    assert text == "Commands:\n/deploy:1 - Deploy app (extension)"


def test_format_coding_commands_filters_session_command_by_query() -> None:
    from loushang.coding.commands.tui import format_coding_commands

    text = asyncio.run(format_coding_commands(_Session(), query="hot"))

    assert text == "Commands:\n/hotkeys - Show all keyboard shortcuts (builtin)"


def test_format_coding_commands_reports_empty_matches() -> None:
    from loushang.coding.commands.tui import format_coding_commands

    text = asyncio.run(format_coding_commands(_Session(), query="missing"))

    assert text == "No commands match: missing"


def test_format_coding_commands_includes_session_argument_hint() -> None:
    from loushang.coding.commands.tui import format_coding_commands

    text = asyncio.run(format_coding_commands(_ArgumentHintSession(), query="review"))

    assert text == "Commands:\n/review <PR-URL> - Review pull request (prompt)"


def test_coding_command_completion_provider_exposes_session_items() -> None:
    from loushang.coding.commands.tui import coding_command_completion_provider
    from loushang.tui import CompletionItem, CompletionProvider

    provider = asyncio.run(coding_command_completion_provider(_Session()))

    assert isinstance(provider, CompletionProvider)
    assert (
        CompletionItem(
            value="/deploy:1", label="/deploy:1", description="Deploy app (extension)"
        )
        in provider.items
    )
    assert (
        CompletionItem(
            value="/hotkeys",
            label="/hotkeys",
            description="Show all keyboard shortcuts (builtin)",
        )
        in provider.items
    )


def test_coding_command_completion_provider_uses_session_argument_hint() -> None:
    from loushang.coding.commands.tui import coding_command_completion_provider
    from loushang.tui import CompletionItem, CompletionProvider

    provider = asyncio.run(coding_command_completion_provider(_ArgumentHintSession()))

    assert isinstance(provider, CompletionProvider)
    assert (
        CompletionItem(
            value="/review",
            label="/review <PR-URL>",
            description="Review pull request (prompt)",
        )
        in provider.items
    )


def test_command_apis_await_session_command_getter() -> None:
    from loushang.coding.commands.tui import coding_command_completion_provider

    coding_provider = asyncio.run(coding_command_completion_provider(_AsyncSession()))

    assert "/inspect" in {item.value for item in coding_provider.items}


def test_format_coding_commands_includes_local_and_session_commands() -> None:
    from loushang.coding.commands.tui import format_coding_commands

    text = asyncio.run(format_coding_commands(_Session(), query="terminal"))

    assert text == "Commands:\n/terminal - Show terminal diagnostics (local)"


def test_coding_command_completion_provider_includes_local_commands() -> None:
    from loushang.coding.commands.tui import coding_command_completion_provider
    from loushang.tui import CompletionItem

    provider = asyncio.run(coding_command_completion_provider(_Session()))

    assert (
        CompletionItem(
            value="/settings",
            label="/settings",
            description="Open settings (local)",
        )
        in provider.items
    )
    assert len([item for item in provider.items if item.value == "/hotkeys"]) == 1


def test_builtin_terminal_command_is_visible_in_command_completion_and_list() -> None:
    from loushang.coding.commands.tui import (
        coding_command_completion_provider,
        format_coding_commands,
    )
    from loushang.tui import CompletionItem

    text = asyncio.run(format_coding_commands(_BuiltinSession(), query="terminal"))
    provider = asyncio.run(coding_command_completion_provider(_BuiltinSession()))

    assert (
        text
        == "Commands:\n/terminal - Show terminal capabilities and protocol diagnostics (builtin)"
    )
    assert (
        CompletionItem(
            value="/terminal",
            label="/terminal",
            description="Show terminal capabilities and protocol diagnostics (builtin)",
        )
        in provider.items
    )


def test_coding_command_palette_includes_structured_session_items() -> None:
    from loushang.coding.commands.tui import coding_command_palette
    from loushang.tui import CommandPaletteItem

    palette = asyncio.run(coding_command_palette(_Session(), title="Commands"))

    assert palette.title == "Commands"
    assert (
        CommandPaletteItem(
            value="/deploy:1", label="/deploy:1", description="Deploy app (extension)"
        )
        in palette.items
    )
    assert (
        CommandPaletteItem(
            value="/hotkeys",
            label="/hotkeys",
            description="Show all keyboard shortcuts (builtin)",
        )
        in palette.items
    )


def test_select_coding_command_uses_palette_when_query_is_empty() -> None:
    from loushang.coding.commands.tui import select_coding_command
    from loushang.tui import CommandPalette

    seen: list[CommandPalette] = []

    async def choose(palette: CommandPalette) -> str:
        seen.append(palette)
        return "/hotkeys"

    result = asyncio.run(select_coding_command(_Session(), choose=choose))

    assert result == "Command selected: /hotkeys"
    assert seen and seen[0].title == "Commands"


def test_select_coding_command_filters_unique_session_match() -> None:
    from loushang.coding.commands.tui import select_coding_command

    result = asyncio.run(select_coding_command(_Session(), query="hot"))

    assert result == "Command selected: /hotkeys"


def test_select_coding_command_reports_multiple_matches() -> None:
    from loushang.coding.commands.tui import select_coding_command

    result = asyncio.run(select_coding_command(_Session(), query="/"))

    assert result.startswith("Multiple commands match:\n")
    assert "  /deploy:1\n" in result
    assert result.endswith("Use /command <full command> to select one.")


def test_select_coding_command_reports_cancelled_palette() -> None:
    from loushang.coding.commands.tui import select_coding_command

    result = asyncio.run(
        select_coding_command(_Session(), choose=lambda _palette: None)
    )

    assert result == "Command selection cancelled."


def test_select_coding_command_invokes_chooser_for_empty_catalog() -> None:
    from loushang.coding.commands.tui import select_coding_command
    from loushang.tui import CommandPalette

    seen: list[CommandPalette] = []

    def cancel(palette: CommandPalette) -> None:
        seen.append(palette)

    cancelled = asyncio.run(
        select_coding_command(
            object(),
            command_catalog=_EmptyCatalog(),  # type: ignore[arg-type]
            choose=cancel,
        )
    )
    missing = asyncio.run(
        select_coding_command(
            object(),
            command_catalog=_EmptyCatalog(),  # type: ignore[arg-type]
            choose=lambda _palette: "/missing",
        )
    )

    assert seen == [CommandPalette((), title="Commands")]
    assert cancelled == "Command selection cancelled."
    assert missing == "No commands match: /missing"
