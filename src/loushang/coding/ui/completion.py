from __future__ import annotations

from pathlib import Path
from typing import Any

from loushang.harnesstui.commands.catalog import snapshot_conversation_command_catalog
from loushang.harnesstui.commands.presentation import command_completion_provider
from loushang.harnesstui.completion.host import (
    CatalogCompletionProfile,
    CatalogSlashAlias,
    PreparedCatalogCompletionHost,
)
from loushang.harnesstui.selection import binding as model_selection_binding
from loushang.tui import (
    CombinedCompletionProvider,
    CompletionProvider,
    SlashCommandCompletionProvider,
)


async def coding_inline_completion_provider(
    session: Any,
    *,
    base_path: Path | None,
) -> SlashCommandCompletionProvider | CombinedCompletionProvider:
    return await coding_completion_host(session).inline_provider(
        base_path=base_path,
    )


def coding_completion_host(session: Any) -> PreparedCatalogCompletionHost:
    return PreparedCatalogCompletionHost(
        command_provider_source=lambda: _coding_command_provider(session),
        model_provider_source=lambda: (
            model_selection_binding.available_session_model_completion_provider(session)
        ),
        profile=_CODING_COMPLETION_PROFILE,
    )


async def _coding_command_provider(session: Any) -> CompletionProvider:
    getter = getattr(session, "list_commands", None)
    catalog = await snapshot_conversation_command_catalog(
        getter if callable(getter) else None
    )
    return command_completion_provider(catalog.commands())


_CODING_COMPLETION_PROFILE = CatalogCompletionProfile(
    model_command_value="/model",
    model_argument_group="Models",
    slash_aliases=(CatalogSlashAlias("/quit", "/exit", "Quit loushang"),),
)
