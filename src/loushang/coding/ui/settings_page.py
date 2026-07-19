from __future__ import annotations

from collections.abc import Callable

from loushang.coding.model_selection_tui import (
    available_model_choices,
    current_model_choice_value,
    select_available_model,
)
from loushang.coding.presentation.settings import (
    apply_coding_setting,
    coding_settings_facts,
)
from loushang.harnesstui.settings.workflow import (
    SettingsConfigUpdate,
    SettingsModelSnapshot,
    SettingsPageView,
    SettingsWorkflowPorts,
)
from loushang.harnesstui.status.line import StatusLinePreviewSnapshot
from loushang.harnesstui.status.provider import StatusProvider
from loushang.tui.settings import ConfigRow


async def build_coding_settings_page(
    *,
    session: object,
    status_provider: StatusProvider,
    usage_provider: Callable[[], object | None] | None = None,
    settings_manager: object | None = None,
    statusline_preview: Callable[[], StatusLinePreviewSnapshot] | None = None,
) -> SettingsPageView:
    """Compose shared settings workflow with Coding-owned facts and actions."""

    async def _load_models() -> SettingsModelSnapshot:
        choices = await available_model_choices(session)
        current_value = await current_model_choice_value(session, choices=choices)
        return SettingsModelSnapshot(tuple(choices), current_value=current_value)

    async def _apply_model(value: str) -> str:
        return await select_available_model(
            session,
            query=value,
            settings_manager=settings_manager,
        )

    return await SettingsPageView.create(
        status_provider=status_provider,
        ports=SettingsWorkflowPorts(
            config_rows=lambda: _coding_config_rows(settings_manager),
            apply_config=lambda item_id, value: _apply_coding_config(
                settings_manager,
                item_id,
                value,
            ),
            load_models=_load_models,
            apply_model=_apply_model,
        ),
        usage_provider=usage_provider,
        statusline_preview=statusline_preview,
    )


def _coding_config_rows(settings_manager: object | None) -> tuple[ConfigRow, ...]:
    return tuple(
        ConfigRow(fact.id, fact.label, fact.value)
        for fact in coding_settings_facts(settings_manager)
    )


def _apply_coding_config(
    settings_manager: object | None,
    item_id: str,
    value: str,
) -> SettingsConfigUpdate | None:
    outcome = apply_coding_setting(settings_manager, item_id, value)
    if not outcome.matched:
        return None
    return SettingsConfigUpdate(outcome.message)


__all__ = ["build_coding_settings_page"]
