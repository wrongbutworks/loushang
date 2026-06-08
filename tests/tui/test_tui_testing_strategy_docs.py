from __future__ import annotations

from pathlib import Path


def test_testing_strategy_documents_composer_selection_manual_smoke() -> None:
    text = Path(
        "docs/internals/architecture/tui/native-terminal-core/testing-strategy.md"
    ).read_text(encoding="utf-8")

    assert "composer-selection-stress" in text
    assert (
        "python -m loushang.coding.ui.playback_runner composer-selection-stress" in text
    )
    assert "Shift+Left" in text
    assert "Shift+Home" in text
    assert "Shift+End" in text
    assert "Ctrl+-" in text


def test_testing_strategy_documents_product_composed_playback() -> None:
    strategy = Path(
        "docs/internals/architecture/tui/native-terminal-core/testing-strategy.md"
    ).read_text(encoding="utf-8")
    playback = Path("docs/internals/testing/native-tui-playback.md").read_text(
        encoding="utf-8"
    )

    for text in (strategy, playback):
        assert "product-composed-interaction" in text
        assert "loushang-product-playback" in text

    assert "assert_last_cursor_on_visible_line" in playback
    assert "logical_cursor" in playback
    assert "screen_cursor" in playback


def test_testing_strategy_documents_streaming_control_and_live_smoke() -> None:
    strategy = Path(
        "docs/internals/architecture/tui/native-terminal-core/testing-strategy.md"
    ).read_text(encoding="utf-8")
    playback = Path("docs/internals/testing/native-tui-playback.md").read_text(
        encoding="utf-8"
    )

    for text in (strategy, playback):
        assert "product-streaming-control-flow" in text
        assert "last frames" in text

    assert "Live Terminal Smoke Checklist" in strategy
    assert "IME candidate window" in strategy
    assert "Kitty, iTerm2, WezTerm, Ghostty, VS Code terminal" in strategy


def test_theme_key_design_lists_editor_selection_token() -> None:
    text = Path(
        "docs/internals/architecture/tui/native-terminal-core/key-designs/KD-009-theme-resolution.md"
    ).read_text(encoding="utf-8")

    assert "editor.selection" in text


def test_terminal_ux_alignment_documents_current_capability_snapshot() -> None:
    text = Path(
        "docs/internals/architecture/tui/native-terminal-core/reference/terminal-ux-feature-alignment.md"
    ).read_text(encoding="utf-8")

    assert "2026-06-05" in text
    assert "Overall qualitative completion" in text
    assert "SelectionController" in text
    assert "Redo storage exists" in text


def test_composer_selection_key_design_records_implemented_status() -> None:
    text = Path(
        "docs/internals/architecture/tui/native-terminal-core/key-designs/KD-017-composer-selection-and-selected-range.md"
    ).read_text(encoding="utf-8")

    assert "Status: Accepted" in text
    assert "implemented as of 2026-06-05" in text
    assert "SelectionController" in text
    assert "TextInput" in text


def test_public_tui_reference_documents_editing_foundation() -> None:
    english = Path("docs/en/reference/tui-editing.md").read_text(encoding="utf-8")
    chinese = Path("docs/zh-CN/reference/tui-editing.md").read_text(encoding="utf-8")
    english_index = Path("docs/en/reference/README.md").read_text(encoding="utf-8")
    chinese_index = Path("docs/zh-CN/reference/README.md").read_text(encoding="utf-8")

    for text in (english, chinese):
        assert "TextInput" in text
        assert "Composer" in text
        assert "SelectionController" in text
        assert "composer-selection-stress" in text
        assert "examples/tui/41_editing_foundation.py" in text

    assert "tui-editing.md" in english_index
    assert "tui-editing.md" in chinese_index


def test_public_tui_reference_documents_runner_and_playback_examples() -> None:
    english_runner = Path("docs/en/reference/tui-runner.md").read_text(
        encoding="utf-8"
    )
    chinese_runner = Path("docs/zh-CN/reference/tui-runner.md").read_text(
        encoding="utf-8"
    )

    for text in (english_runner, chinese_runner):
        assert "examples/tui/40_runner_basic.py" in text
        assert "examples/tui/42_playback_smoke.py" in text
        assert "PlaybackHarness" in text
