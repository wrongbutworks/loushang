from __future__ import annotations

from dataclasses import dataclass, field

from loushang.coding.ui.settings_common import (
    SETTINGS_PAGE_THEME,
    SETTINGS_VALUE_COLUMN,
    ConfigRow,
    bool_text,
    config_items,
    is_space_event,
    is_tab_fallback_key,
    next_bool_value,
    row_for_key,
    settings_header,
)
from loushang.tui import (
    CursorDeclaration,
    InputIntent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    SearchableList,
    SearchableListSelect,
)


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


@dataclass(slots=True)
class ConfigSettingsPage:
    rows: tuple[ConfigRow, ...]
    focused: bool = False
    settings: SearchableList = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self._make_list(focused=False)

    def focus(self) -> None:
        self.focused = True
        self.settings.focus()

    def blur(self) -> None:
        self.focused = False
        self.settings.blur()

    def editor_input_target(self) -> object | None:
        return self.settings.editor_input_target()

    def set_rows(self, rows: tuple[ConfigRow, ...], *, preserve_active_key: str = "") -> None:
        self.rows = rows
        self.settings.set_items(config_items(rows), preserve_active_key=preserve_active_key)

    def handle_input(self, event: object) -> object:
        result = self.settings.handle_input(event)
        if isinstance(result, SearchableListSelect):
            return self._setting_intent(result.key)
        if result is not None:
            return result
        if self.settings.focus_region == "list" and is_space_event(event):
            item = self.settings.active_item
            if item is not None:
                return self._setting_intent(item.key)
        if is_tab_fallback_key(event):
            return True
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        if constraints.max_height <= 4:
            return self.settings.render(constraints)
        result = self.settings.render(
            RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2))
        )
        header = RenderLine(settings_header(constraints.width))
        rows = [*result.lines[:3], RenderLine(""), header, *result.lines[3:]]
        cursor = result.cursor
        if cursor is not None and cursor.row >= 3:
            cursor = CursorDeclaration(row=cursor.row + 2, column=cursor.column)
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

    def _make_list(self, *, focused: bool) -> SearchableList:
        return SearchableList(
            config_items(self.rows),
            placeholder="Search settings...",
            empty_text="No matching settings",
            focused=focused,
            search_box=True,
            detail_column=SETTINGS_VALUE_COLUMN,
            theme=SETTINGS_PAGE_THEME,
        )

    def _setting_intent(self, key: str) -> InputIntent | None:
        row = row_for_key(self.rows, key)
        if row is None or row.disabled:
            return None
        value = next_bool_value(row.value)
        return InputIntent(kind="setting", text=row.id, note=value)


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
