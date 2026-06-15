from __future__ import annotations

from pathlib import Path


def test_widget_reference_marks_settings_surface_as_legacy_compatibility() -> None:
    for path in (
        Path("docs/en/reference/tui-widgets.md"),
        Path("docs/zh-CN/reference/tui-widgets.md"),
    ):
        text = path.read_text(encoding="utf-8")

        assert "SettingsSurface" in text
        assert "legacy compatibility" in text.casefold()
        assert "PageScaffold" in text
        assert "SearchableList" in text
        assert "SettingsList" in text
