from __future__ import annotations

from dataclasses import dataclass

from loushang.harnesstui.settings.page import ConfigSettingsPage as ConfigSettingsPage
from loushang.tui.settings import ConfigRow, bool_text


@dataclass(frozen=True, slots=True)
class ManagerBoolConfig:
    id: str
    label: str
    getter: str
    setter: str
    status_label: str


_MANAGER_BOOL_CONFIGS = (
    ManagerBoolConfig(
        "terminal.progress",
        "Terminal progress",
        "get_show_terminal_progress",
        "set_show_terminal_progress",
        "Terminal progress",
    ),
    ManagerBoolConfig(
        "terminal.show_images",
        "Show images",
        "get_show_images",
        "set_show_images",
        "Show images",
    ),
    ManagerBoolConfig(
        "terminal.clear_on_shrink",
        "Clear on shrink",
        "get_clear_on_shrink",
        "set_clear_on_shrink",
        "Clear on shrink",
    ),
    ManagerBoolConfig(
        "images.auto_resize",
        "Image auto-resize",
        "get_image_auto_resize",
        "set_image_auto_resize",
        "Image auto-resize",
    ),
    ManagerBoolConfig(
        "images.block_images",
        "Block images",
        "get_block_images",
        "set_block_images",
        "Block images",
    ),
    ManagerBoolConfig(
        "retry.enabled",
        "Retry",
        "get_retry_enabled",
        "set_retry_enabled",
        "Retry",
    ),
)


def config_rows(settings_manager: object | None) -> tuple[ConfigRow, ...]:
    rows = []
    if settings_manager is not None:
        for config in _MANAGER_BOOL_CONFIGS:
            getter = getattr(settings_manager, config.getter, None)
            if callable(getter):
                rows.append(ConfigRow(config.id, config.label, bool_text(bool(getter()))))
    return tuple(rows)


def manager_bool_config(item_id: str) -> ManagerBoolConfig | None:
    for config in _MANAGER_BOOL_CONFIGS:
        if config.id == item_id:
            return config
    return None
