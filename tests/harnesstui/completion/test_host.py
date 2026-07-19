from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.harnesstui.completion.host import (
    CatalogCompletionProfile,
    CatalogSlashAlias,
    PreparedCatalogCompletionHost,
)
from loushang.tui import CompletionItem, CompletionProvider


def _profile() -> CatalogCompletionProfile:
    return CatalogCompletionProfile(
        model_command_value="/choose-model",
        model_argument_group="Prepared models",
        slash_aliases=(
            CatalogSlashAlias(
                trigger_value="/quit",
                value="/leave",
                description="Leave this product",
            ),
        ),
    )


def _host() -> PreparedCatalogCompletionHost:
    async def commands() -> CompletionProvider:
        await asyncio.sleep(0)
        return CompletionProvider(
            (
                CompletionItem(
                    value="/choose-model",
                    label="/choose-model",
                    description="Choose a prepared model",
                ),
                CompletionItem(value="/quit", description="Quit"),
            )
        )

    return PreparedCatalogCompletionHost(
        command_provider_source=commands,
        model_provider_source=lambda: CompletionProvider(
            (CompletionItem(value="provider/model", label="A model"),)
        ),
        profile=_profile(),
    )


def test_prepared_completion_host_builds_arguments_and_product_aliases() -> None:
    provider = asyncio.run(_host().slash_provider())

    assert tuple(command.name for command in provider.commands) == (
        "/choose-model",
        "/quit",
        "leave",
    )
    assert provider.commands[0].argument_group == "Prepared models"
    assert [item.value for item in provider.complete("/choose-model pro")] == [
        "/choose-model provider/model"
    ]
    assert [item.value for item in provider.complete("/lea")] == ["/leave"]


def test_prepared_completion_host_limits_input_completion_to_slash_context() -> None:
    host = _host()

    assert asyncio.run(host.complete("plain prompt")) == ()
    assert asyncio.run(host.complete("/choose-model pro")) == (
        CompletionItem(
            value="/choose-model provider/model",
            label="A model",
        ),
    )


def test_prepared_completion_host_optionally_composes_recursive_path_source(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "example.py").write_text("", encoding="utf-8")

    slash_only = asyncio.run(_host().inline_provider())
    combined = asyncio.run(_host().inline_provider(base_path=tmp_path))

    assert [item.value for item in slash_only.complete("/lea")] == ["/leave"]
    suggestions = combined.get_suggestions(("@example",), 0, len("@example"))
    assert suggestions is not None
    assert [item.value for item in suggestions.items] == ["@src/example.py"]
