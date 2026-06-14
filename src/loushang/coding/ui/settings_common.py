from __future__ import annotations

from dataclasses import dataclass

from loushang.tui import SearchableListItem, ThemeResolver, truncate_to_width


@dataclass(frozen=True, slots=True)
class ConfigRow:
    id: str
    label: str
    value: str
    description: str = ""
    disabled: bool = False


SETTINGS_VALUE_COLUMN = 42

SETTINGS_PAGE_THEME = ThemeResolver(
    defaults={
        "widget.tabs.tab": {"color": "white"},
        "widget.tabs.selected": {"bold": True, "color": "green"},
        "widget.tabs.level0.selected_header_focus": {"bold": True, "color": "cyan"},
        "widget.tabs.level0.selected_content_focus": {"bold": True, "color": "green"},
        "widget.tabs.level1.selected_header_focus": {"bold": True, "color": "magenta"},
        "widget.tabs.level1.selected_content_focus": {"bold": True, "color": "yellow"},
        "widget.searchableList.search": {"color": "white"},
        "widget.searchableList.placeholder": {"color": "bright_black"},
        "widget.searchableList.item": {"color": "white"},
        "widget.searchableList.focus": {"bold": True, "color": "cyan"},
        "widget.searchableList.disabled": {"dim": True},
        "widget.searchableList.description": {"color": "bright_black"},
        "widget.searchableList.empty": {"color": "bright_black"},
        "widget.searchableList.overflow": {"color": "bright_black"},
    }
)


def config_items(rows: tuple[ConfigRow, ...]) -> tuple[SearchableListItem, ...]:
    return tuple(
        SearchableListItem(row.id, row.label, row.value, row.description, disabled=row.disabled)
        for row in rows
    )


def row_for_key(rows: tuple[ConfigRow, ...], key: str) -> ConfigRow | None:
    for row in rows:
        if row.id == key:
            return row
    return None


def settings_header(width: int) -> str:
    value_column = max(8, min(SETTINGS_VALUE_COLUMN, max(8, width - 8)))
    return truncate_to_width(f"{'Setting':<{value_column}}Value", max_width=width, ellipsis="")


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def as_bool(value: str) -> bool | None:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def next_bool_value(value: str) -> str:
    current = as_bool(value)
    if current is None:
        return value
    return bool_text(not current)


def is_space_event(event: object) -> bool:
    return (
        getattr(event, "kind", "") == "key"
        and getattr(event, "key", "") == "space"
    ) or (
        getattr(event, "kind", "") == "text"
        and getattr(event, "text", "") == " "
    )


def is_tab_fallback_key(event: object) -> bool:
    return getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"left", "right", "home", "end"}
