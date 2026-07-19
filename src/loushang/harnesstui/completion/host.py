from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from loushang.tui import (
    CombinedCompletionProvider,
    CompletionItem,
    CompletionProvider,
    PathCompletionProvider,
    SlashCommand,
    SlashCommandCompletionProvider,
)

CompletionProviderSource = Callable[
    [], CompletionProvider | Awaitable[CompletionProvider]
]


@dataclass(frozen=True, slots=True)
class CatalogSlashAlias:
    """A product-declared alias enabled by another prepared command."""

    trigger_value: str
    value: str
    description: str


@dataclass(frozen=True, slots=True)
class CatalogCompletionProfile:
    """Product policy and wording for prepared catalog completion."""

    model_command_value: str
    model_argument_group: str
    slash_aliases: tuple[CatalogSlashAlias, ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedCatalogCompletionHost:
    """Build slash and inline completion without access to product runtime data."""

    command_provider_source: CompletionProviderSource
    model_provider_source: CompletionProviderSource
    profile: CatalogCompletionProfile

    async def complete(self, text: str) -> tuple[CompletionItem, ...]:
        provider = await self.input_provider(text)
        return tuple(provider.items)

    async def input_provider(self, text: str) -> CompletionProvider:
        if not text.strip().startswith("/"):
            return CompletionProvider(())
        provider = await self.slash_provider()
        return CompletionProvider(provider.complete(text.lstrip()))

    async def inline_provider(
        self,
        *,
        base_path: Path | None = None,
    ) -> SlashCommandCompletionProvider | CombinedCompletionProvider:
        provider = await self.slash_provider()
        if base_path is None:
            return provider
        return CombinedCompletionProvider(
            (
                provider,
                PathCompletionProvider(base_path=base_path, recursive=True),
            )
        )

    async def slash_provider(self) -> SlashCommandCompletionProvider:
        command_provider = await _resolve_provider(self.command_provider_source)
        model_provider = await _resolve_provider(self.model_provider_source)
        commands = [
            SlashCommand(
                name=item.value,
                label=item.display_label(),
                description=item.description,
                argument_provider=(
                    model_provider
                    if item.value == self.profile.model_command_value
                    else None
                ),
                argument_group=(
                    self.profile.model_argument_group
                    if item.value == self.profile.model_command_value
                    else ""
                ),
            )
            for item in command_provider.items
        ]
        command_values = {item.value for item in command_provider.items}
        commands.extend(
            SlashCommand(
                name=alias.value.removeprefix("/"),
                label=alias.value,
                description=alias.description,
            )
            for alias in self.profile.slash_aliases
            if alias.trigger_value in command_values
            and alias.value not in command_values
        )
        return SlashCommandCompletionProvider(tuple(commands))


async def _resolve_provider(source: CompletionProviderSource) -> CompletionProvider:
    provider = source()
    if inspect.isawaitable(provider):
        return await provider
    return provider


__all__ = [
    "CatalogCompletionProfile",
    "CatalogSlashAlias",
    "CompletionProviderSource",
    "PreparedCatalogCompletionHost",
]
