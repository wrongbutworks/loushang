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
from loushang.tui import CompletionItem, CompletionProvider


async def complete_coding_input(session: Any, text: str) -> tuple[CompletionItem, ...]:
    return await _coding_completion_host(session).complete(text)


async def coding_input_completion_provider(
    session: Any, text: str
) -> CompletionProvider:
    return await _coding_completion_host(session).input_provider(text)


async def coding_inline_completion_provider(
    session: Any,
) -> Any:
    return await _coding_completion_host(session).inline_provider(
        base_path=_session_completion_base_path(session),
    )


def _coding_completion_host(session: Any) -> PreparedCatalogCompletionHost:
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


def _session_completion_base_path(session: Any) -> Path | None:
    for manager_name in ("session_manager", "sessionManager"):
        manager = getattr(session, manager_name, None)
        get_cwd = getattr(manager, "get_cwd", None)
        if not callable(get_cwd):
            continue
        try:
            cwd = get_cwd()
        except Exception:
            continue
        if not cwd:
            continue
        path = Path(str(cwd)).expanduser()
        if path.is_dir():
            return path
    return None


__all__ = [
    "coding_inline_completion_provider",
    "coding_input_completion_provider",
    "complete_coding_input",
]
