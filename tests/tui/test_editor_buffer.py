from __future__ import annotations

from loushang.tui.editor_buffer import EditorBuffer


def test_editor_buffer_inserts_text_and_tracks_grapheme_cursor() -> None:
    buffer = EditorBuffer()

    buffer.insert_text("a中e\u0301")

    assert buffer.value == "a中e\u0301"
    assert len(buffer) == 3
    assert buffer.cursor == 3

    assert buffer.move_left()
    buffer.insert_text("🙂")

    assert buffer.value == "a中🙂e\u0301"
    assert len(buffer) == 4
    assert buffer.cursor == 3


def test_editor_buffer_deletes_grapheme_clusters_atomically() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("a👨\u200d👩\u200d👧\u200d👦e\u0301")

    assert len(buffer) == 3

    assert buffer.move_left()
    assert buffer.delete_backward()

    assert buffer.value == "ae\u0301"
    assert len(buffer) == 2
    assert buffer.cursor == 1

    assert buffer.delete_forward()
    assert buffer.value == "a"
    assert buffer.cursor == 1


def test_editor_buffer_moves_to_line_boundaries_and_empty_lines_are_noops() -> None:
    buffer = EditorBuffer()
    buffer.set_text("ab\n\ncd")

    assert buffer.move_to_line_start()
    assert buffer.cursor == 4
    assert not buffer.move_to_line_start()

    assert buffer.move_to_start()
    for _ in range(3):
        assert buffer.move_right()

    assert buffer.cursor == 3
    assert not buffer.move_to_line_start()
    assert not buffer.move_to_line_end()

    assert buffer.move_right()
    assert buffer.move_to_line_end()
    assert buffer.cursor == 6


def test_editor_buffer_delete_methods_return_change_status() -> None:
    buffer = EditorBuffer()

    assert not buffer.delete_backward()
    assert not buffer.delete_forward()

    buffer.insert_text("ab")
    assert buffer.move_left()

    assert buffer.delete_forward()
    assert buffer.value == "a"

    assert buffer.delete_backward()
    assert buffer.value == ""
    assert not buffer.delete_backward()
    assert not buffer.delete_forward()


def test_editor_buffer_undo_redo_tracks_text_edits_not_cursor_movement() -> None:
    buffer = EditorBuffer()

    buffer.insert_text("abc")
    assert buffer.move_left()
    buffer.insert_text("X")

    assert buffer.value == "abXc"
    assert buffer.cursor == 3

    assert buffer.undo()
    assert buffer.value == "abc"
    assert buffer.cursor == 2

    assert buffer.undo()
    assert buffer.value == ""
    assert buffer.cursor == 0

    assert not buffer.undo()

    assert buffer.redo()
    assert buffer.value == "abc"
    assert buffer.cursor == 2

    assert buffer.redo()
    assert buffer.value == "abXc"
    assert buffer.cursor == 3

    assert not buffer.redo()


def test_editor_buffer_programmatic_resets_clear_undo_and_redo() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("abc")
    assert buffer.undo()
    assert buffer.redo()

    buffer.set_text("reset")

    assert buffer.value == "reset"
    assert buffer.cursor == len(buffer)
    assert not buffer.undo()
    assert not buffer.redo()

    buffer.insert_text("!")
    assert buffer.undo()
    assert buffer.value == "reset"

    buffer.clear()

    assert buffer.value == ""
    assert buffer.cursor == 0
    assert len(buffer) == 0
    assert not buffer.undo()
    assert not buffer.redo()


def test_editor_buffer_cursor_stays_within_bounds() -> None:
    buffer = EditorBuffer()

    assert not buffer.move_left()
    assert not buffer.move_to_start()
    assert not buffer.move_to_end()

    buffer.insert_text("ab")

    assert buffer.cursor == 2
    assert not buffer.move_right()
    assert not buffer.move_to_end()

    assert buffer.move_to_start()
    assert buffer.cursor == 0
    assert not buffer.move_left()
    assert not buffer.move_to_start()

    assert buffer.move_to_end()
    assert buffer.cursor == len(buffer)
