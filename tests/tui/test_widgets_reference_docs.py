from __future__ import annotations

from pathlib import Path


def test_widget_reference_recommends_composed_settings_pages_without_legacy_primitives() -> None:
    removed_names = (
        "SettingsSurface",
        "SettingItem",
        "SettingsList",
        "SettingsListRenderer",
    )

    for path in (
        Path("docs/en/reference/tui-widgets.md"),
        Path("docs/zh-CN/reference/tui-widgets.md"),
    ):
        text = path.read_text(encoding="utf-8")

        assert "PageScaffold" in text
        assert "SearchableList" in text
        assert "DataGrid" in text
        assert "DataGridColumn" in text
        assert "widget.dataGrid.focusCell" in text
        for name in removed_names:
            assert name not in text
