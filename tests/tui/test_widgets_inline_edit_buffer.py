from __future__ import annotations

from loushang.tui.ui_parts.widgets._inline_edit_buffer import InlineEditBuffer


def test_inline_edit_buffer_initial_value_is_selected_and_replaced_by_text() -> None:
    buffer = InlineEditBuffer.from_value("123")

    assert buffer.text == "123"
    assert buffer.cursor == 3
    assert buffer.selected is True

    assert buffer.insert_text("9") is True

    assert buffer.text == "9"
    assert buffer.cursor == 1
    assert buffer.selected is False


def test_inline_edit_buffer_moves_and_edits_by_grapheme_clusters() -> None:
    buffer = InlineEditBuffer("a🙂c", cursor=3)

    assert buffer.move_left() is True
    assert buffer.cursor == 2
    assert buffer.insert_text("X") is True
    assert buffer.text == "a🙂Xc"
    assert buffer.cursor == 3
    assert buffer.text_before_cursor() == "a🙂X"

    assert buffer.delete_backward() is True
    assert buffer.text == "a🙂c"
    assert buffer.cursor == 2

    assert buffer.delete_forward() is True
    assert buffer.text == "a🙂"
    assert buffer.cursor == 2


def test_inline_edit_buffer_selected_delete_and_backspace_clear_text() -> None:
    backspace_buffer = InlineEditBuffer.from_value("abc")
    delete_buffer = InlineEditBuffer.from_value("abc")

    assert backspace_buffer.delete_backward() is True
    assert backspace_buffer.text == ""
    assert backspace_buffer.cursor == 0
    assert backspace_buffer.selected is False

    assert delete_buffer.delete_forward() is True
    assert delete_buffer.text == ""
    assert delete_buffer.cursor == 0
    assert delete_buffer.selected is False


def test_inline_edit_buffer_selected_arrow_moves_to_edge_and_clears_selection() -> None:
    buffer = InlineEditBuffer.from_value("abc")

    assert buffer.move_left() is True
    assert buffer.cursor == 0
    assert buffer.selected is False

    buffer = InlineEditBuffer.from_value("abc")

    assert buffer.move_right() is True
    assert buffer.cursor == 3
    assert buffer.selected is False
