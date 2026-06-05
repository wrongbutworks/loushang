from __future__ import annotations

from pathlib import Path


def test_testing_strategy_documents_composer_selection_manual_smoke() -> None:
    text = Path("docs/internals/architecture/tui/native-terminal-core/testing-strategy.md").read_text(
        encoding="utf-8"
    )

    assert "composer-selection-stress" in text
    assert "python -m loushang.coding.ui.playback_runner composer-selection-stress" in text
    assert "Shift+Left" in text
    assert "Shift+Home" in text
    assert "Shift+End" in text
    assert "Ctrl+-" in text


def test_theme_key_design_lists_editor_selection_token() -> None:
    text = Path("docs/internals/architecture/tui/native-terminal-core/key-designs/KD-009-theme-resolution.md").read_text(
        encoding="utf-8"
    )

    assert "editor.selection" in text
