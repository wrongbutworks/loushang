from __future__ import annotations

from dataclasses import dataclass, field

from loushang.tui import (
    CursorDeclaration,
    InputIntent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    SearchableList,
    SearchableListSelect,
)
from loushang.tui.settings import (
    SETTINGS_PAGE_THEME,
    SETTINGS_VALUE_COLUMN,
    ConfigRow,
    config_items,
    is_space_event,
    is_tab_fallback_key,
    next_bool_value,
    row_for_key,
    settings_header,
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
