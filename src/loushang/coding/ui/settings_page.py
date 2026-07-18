from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loushang.coding.ui.model_list import (
    available_model_choices,
    current_model_choice_value,
    select_available_model,
)
from loushang.coding.ui.settings_config import (
    config_rows,
    manager_bool_config,
)
from loushang.coding.ui.status_provider import CodingTuiStatusProvider
from loushang.harnesstui.selection.catalog import ModelChoice
from loushang.harnesstui.settings.dashboard import (
    SettingsDashboard,
    StaticLinesPage,
    model_usage_lines,
    stats_overview_lines,
    status_lines,
    usage_lines,
)
from loushang.harnesstui.settings.model import ModelPage
from loushang.harnesstui.settings.page import ConfigSettingsPage
from loushang.harnesstui.status.line import (
    StatusLinePreviewSnapshot,
    StatusLineSettings,
)
from loushang.harnesstui.status.settings import StatusLineSettingsPage
from loushang.tui import TabGroup, TabPage
from loushang.tui.settings import (
    SETTINGS_PAGE_THEME,
    ConfigRow,
    as_bool,
)

__all__ = [
    "ConfigRow",
    "ConfigSettingsPage",
    "ModelPage",
    "SettingsApplyResult",
    "SettingsPageView",
]


@dataclass(frozen=True, slots=True)
class SettingsApplyResult:
    message: str
    statusline_visible: bool | None = None
    statusline_settings: StatusLineSettings | None = None
    refresh_model_label: bool = False


@dataclass(slots=True)
class SettingsPageView(SettingsDashboard):
    session: Any
    status_provider: CodingTuiStatusProvider
    settings_manager: object | None = None
    usage_provider: Callable[[], object | None] | None = None
    status_page: StaticLinesPage = field(init=False)
    config_page: ConfigSettingsPage = field(init=False)
    model_page: ModelPage = field(init=False)
    statusline_page: StatusLineSettingsPage = field(init=False)
    usage_page: StaticLinesPage = field(init=False)
    stats_page: TabGroup = field(init=False)
    statusline_preview: Callable[[], StatusLinePreviewSnapshot] | None = None

    @classmethod
    async def create(
        cls,
        *,
        session: Any,
        status_provider: CodingTuiStatusProvider,
        usage_provider: Callable[[], object | None] | None = None,
        settings_manager: object | None = None,
        session_settings: object | None = None,
        statusline_preview: Callable[[], StatusLinePreviewSnapshot] | None = None,
    ) -> SettingsPageView:
        del session_settings
        view = cls(
            session=session,
            status_provider=status_provider,
            settings_manager=settings_manager,
            usage_provider=usage_provider,
            statusline_preview=statusline_preview,
        )
        await view._build()
        view.focus()
        return view

    async def apply_setting(self, item_id: str, value: str) -> SettingsApplyResult:
        if item_id == "statusline" or item_id.startswith("statusline."):
            message = self.status_provider.apply_statusline_setting(item_id, value)
            self._refresh_status_page()
            self._refresh_statusline_page(preserve_active_key=item_id)
            settings = self.status_provider.statusline_settings()
            self.feedback_message = message
            return SettingsApplyResult(
                message,
                statusline_visible=settings.enabled,
                statusline_settings=settings,
            )
        config = manager_bool_config(item_id)
        if config is not None:
            enabled = as_bool(value)
            if enabled is None:
                message = f"Invalid {config.label} value."
                self.feedback_message = message
                return SettingsApplyResult(message)
            setter = getattr(self.settings_manager, config.setter, None)
            if not callable(setter):
                message = f"{config.status_label} is not available."
                self.feedback_message = message
                return SettingsApplyResult(message)
            setter(enabled)
            self._refresh_config_rows(preserve_active_key=config.id)
            message = f"{config.status_label}: {'on' if enabled else 'off'}"
            self.feedback_message = message
            return SettingsApplyResult(message)
        if item_id == "model.current":
            message = await select_available_model(
                self.session,
                query=value,
                settings_manager=self.settings_manager,
            )
            await self._refresh_model_page()
            self._refresh_status_page()
            self.feedback_message = message
            return SettingsApplyResult(message, refresh_model_label=True)
        message = f"Unknown setting: {item_id}"
        self.feedback_message = message
        return SettingsApplyResult(message)

    async def _build(self) -> None:
        self.status_page = StaticLinesPage(status_lines(self.status_provider.snapshot()))
        self.config_page = ConfigSettingsPage(config_rows(self.settings_manager))
        choices, current_value, error = await _load_model_choices(self.session)
        self.model_page = ModelPage(choices, current_value=current_value, error=error)
        self.statusline_page = StatusLineSettingsPage(
            self.status_provider.statusline_settings(),
            self._statusline_preview_snapshot,
        )
        self.usage_page = StaticLinesPage(usage_lines(self.usage_provider))
        self.stats_page = TabGroup(
            (
                TabPage("overview", "Overview", StaticLinesPage(stats_overview_lines(self.status_provider.snapshot()))),
                TabPage("model-usage", "Model Usage", StaticLinesPage(model_usage_lines(current_value))),
            ),
            value="overview",
            level=1,
            theme=SETTINGS_PAGE_THEME,
        )
        self.tabs = TabGroup(
            (
                TabPage("status", "Status", self.status_page),
                TabPage("config", "Config", self.config_page),
                TabPage("model", "Model", self.model_page),
                TabPage("status-line", "Status Line", self.statusline_page),
                TabPage("usage", "Usage", self.usage_page),
                TabPage("stats", "Stats", self.stats_page),
            ),
            value="config",
            theme=SETTINGS_PAGE_THEME,
        )

    def _refresh_status_page(self) -> None:
        self.status_page.lines = status_lines(self.status_provider.snapshot())

    def _refresh_config_rows(self, *, preserve_active_key: str = "") -> None:
        self.config_page.set_rows(config_rows(self.settings_manager), preserve_active_key=preserve_active_key)

    def _refresh_statusline_page(self, *, preserve_active_key: str = "") -> None:
        self.statusline_page.set_statusline_settings(
            self.status_provider.statusline_settings(),
            preserve_active_key=preserve_active_key,
        )

    async def _refresh_model_page(self) -> None:
        choices, current_value, error = await _load_model_choices(self.session)
        self.model_page.set_choices(choices, current_value=current_value, error=error)
        selected = self.stats_page.selected_page
        if selected is not None and isinstance(selected.content, StaticLinesPage):
            selected.content.lines = model_usage_lines(current_value)

    def _statusline_preview_snapshot(self) -> StatusLinePreviewSnapshot:
        if self.statusline_preview is not None:
            return self.statusline_preview()
        snapshot = self.status_provider.snapshot()
        return StatusLinePreviewSnapshot(
            model_label=snapshot.model_label,
            cwd=snapshot.cwd,
            branch=snapshot.branch,
            session_label=snapshot.session_label,
            running=snapshot.running,
        )


async def _load_model_choices(session: Any) -> tuple[tuple[ModelChoice, ...], str | None, str]:
    try:
        choices = await available_model_choices(session)
        current_value = await current_model_choice_value(session, choices=choices)
    except Exception as error:
        return (), None, str(error)
    return tuple(choices), current_value, ""
