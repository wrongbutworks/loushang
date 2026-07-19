from __future__ import annotations

from pathlib import Path
from typing import Any

from loushang.coding.commands.tui import coding_command_completion_provider
from loushang.coding.model_selection_tui import available_model_completion_provider
from loushang.harnesstui.completion.host import (
    CatalogCompletionProfile,
    CatalogSlashAlias,
    PreparedCatalogCompletionHost,
)
from loushang.tui import CombinedCompletionProvider, SlashCommandCompletionProvider


async def coding_inline_completion_provider(
    session: Any,
    *,
    base_path: Path | None,
) -> SlashCommandCompletionProvider | CombinedCompletionProvider:
    return await coding_completion_host(session).inline_provider(
        base_path=base_path,
    )


def coding_completion_host(session: Any) -> PreparedCatalogCompletionHost:
    """Bind Coding catalog sources to the shared completion host."""

    return PreparedCatalogCompletionHost(
        command_provider_source=lambda: coding_command_completion_provider(session),
        model_provider_source=lambda: available_model_completion_provider(session),
        profile=_CODING_COMPLETION_PROFILE,
    )


_CODING_COMPLETION_PROFILE = CatalogCompletionProfile(
    model_command_value="/model",
    model_argument_group="Models",
    slash_aliases=(CatalogSlashAlias("/quit", "/exit", "Quit loushang"),),
)


__all__ = [
    "coding_completion_host",
    "coding_inline_completion_provider",
]
