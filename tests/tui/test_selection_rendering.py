from __future__ import annotations

from loushang.tui import (
    DEFAULT_SELECTION_STYLE,
    SelectionController,
)
from loushang.tui import (
    highlight_selection_by_columns as exported_highlight_selection_by_columns,
)
from loushang.tui.cell_width import strip_control_sequences
from loushang.tui.selection_rendering import highlight_selection_by_columns


def test_highlight_selection_by_columns_applies_style_at_display_boundaries() -> None:
    rendered = highlight_selection_by_columns(
        "你🙂ab",
        selection_range=(2, 4),
        selection_style={"reverse": True},
    )

    assert rendered == "你\x1b[7m🙂\x1b[27mab"
    assert strip_control_sequences(rendered) == "你🙂ab"


def test_highlight_selection_by_columns_ignores_empty_or_missing_selection() -> None:
    assert highlight_selection_by_columns("abc", selection_range=None) == "abc"
    assert highlight_selection_by_columns("abc", selection_range=(1, 1)) == "abc"


def test_selection_foundation_helpers_are_exported_from_tui_package() -> None:
    assert DEFAULT_SELECTION_STYLE == {"reverse": True}
    assert SelectionController.__module__ == "loushang.tui.selection_controller"
    assert exported_highlight_selection_by_columns is highlight_selection_by_columns
