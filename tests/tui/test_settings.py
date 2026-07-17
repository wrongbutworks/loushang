from __future__ import annotations

from types import SimpleNamespace

from loushang.tui import SearchableListItem, visible_width
from loushang.tui import settings as tui_settings


def test_config_rows_build_searchable_items_and_lookup_by_key() -> None:
    rows = (
        tui_settings.ConfigRow("enabled", "Enabled", "true"),
        tui_settings.ConfigRow("locked", "Locked", "false", "Managed", disabled=True),
    )

    assert tui_settings.config_items(rows) == (
        SearchableListItem("enabled", "Enabled", "true", "", disabled=False),
        SearchableListItem("locked", "Locked", "false", "Managed", disabled=True),
    )
    assert tui_settings.row_for_key(rows, "locked") is rows[1]
    assert tui_settings.row_for_key(rows, "missing") is None


def test_settings_input_and_boolean_helpers_preserve_existing_contract() -> None:
    assert tui_settings.as_bool("TRUE") is True
    assert tui_settings.as_bool("false") is False
    assert tui_settings.as_bool("auto") is None
    assert tui_settings.next_bool_value("true") == "false"
    assert tui_settings.next_bool_value("false") == "true"
    assert tui_settings.next_bool_value("auto") == "auto"
    assert tui_settings.is_space_event(SimpleNamespace(kind="key", key="space"))
    assert tui_settings.is_space_event(SimpleNamespace(kind="text", text=" "))
    assert tui_settings.is_tab_fallback_key(SimpleNamespace(kind="key", key="left"))
    assert not tui_settings.is_tab_fallback_key(SimpleNamespace(kind="key", key="tab"))


def test_settings_header_respects_available_width() -> None:
    assert tui_settings.settings_header(80) == f"{'Setting':<42}Value"
    assert visible_width(tui_settings.settings_header(12)) <= 12
