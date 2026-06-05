from __future__ import annotations

from loushang.tui.selection import SelectionRange


def test_selection_range_normalizes_forward_and_backward_bounds() -> None:
    assert SelectionRange(anchor=1, focus=4).normalized(10) == (1, 4)
    assert SelectionRange(anchor=4, focus=1).normalized(10) == (1, 4)


def test_selection_range_clamps_to_buffer_length_and_detects_empty() -> None:
    selection = SelectionRange(anchor=-4, focus=12)

    assert selection.start == -4
    assert selection.end == 12
    assert selection.normalized(5) == (0, 5)
    assert not selection.is_empty
    assert SelectionRange(anchor=3, focus=3).is_empty
