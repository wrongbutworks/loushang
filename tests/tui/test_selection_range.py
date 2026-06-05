from __future__ import annotations

from loushang.tui.selection import SelectionRange
from loushang.tui.selection_controller import SelectionController


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


def test_selection_controller_tracks_anchor_focus_and_moves_cursor() -> None:
    cursor = 3

    def set_cursor(value: int) -> None:
        nonlocal cursor
        cursor = value

    controller = SelectionController(
        length=lambda: 5,
        cursor=lambda: cursor,
        set_cursor=set_cursor,
    )

    controller.extend_to(1)

    assert cursor == 1
    assert controller.selected_range == (1, 3)

    controller.extend_to(-10)

    assert cursor == 0
    assert controller.selected_range == (0, 3)

    controller.set(2, 2)

    assert cursor == 2
    assert controller.selected_range is None
