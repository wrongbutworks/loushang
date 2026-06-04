from __future__ import annotations

import pytest

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


def test_max_undo_depth_limits_snapshots() -> None:
    buffer = EditorBuffer(max_undo_depth=3)

    for ch in "abcd":
        buffer.insert_text(ch)

    assert buffer.value == "abcd"

    assert buffer.undo()
    assert buffer.value == "abc"
    assert buffer.undo()
    assert buffer.value == "ab"
    assert buffer.undo()
    assert buffer.value == "a"
    assert not buffer.undo()


def test_max_undo_depth_none_is_unlimited() -> None:
    buffer = EditorBuffer(max_undo_depth=None)

    for ch in "abcdefghij":
        buffer.insert_text(ch)

    for _ in range(10):
        assert buffer.undo()

    assert buffer.value == ""
    assert not buffer.undo()


def test_max_undo_depth_must_be_positive_when_set() -> None:
    with pytest.raises(ValueError, match="max_undo_depth"):
        EditorBuffer(max_undo_depth=0)

    with pytest.raises(ValueError, match="max_undo_depth"):
        EditorBuffer(max_undo_depth=-1)


def test_text_before_and_after_cursor_reflect_grapheme_position() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("a中e\u0301")

    assert buffer.text_before_cursor == "a中e\u0301"
    assert buffer.text_after_cursor == ""

    buffer.move_left()
    assert buffer.text_before_cursor == "a中"
    assert buffer.text_after_cursor == "e\u0301"

    buffer.move_to_start()
    assert buffer.text_before_cursor == ""
    assert buffer.text_after_cursor == "a中e\u0301"


def test_delete_range_removes_and_returns_text() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("hello world")

    removed = buffer.delete_range(1, 4)

    assert removed == "ell"
    assert buffer.value == "ho world"
    assert buffer.cursor == 1


def test_delete_range_empty_is_noop_and_preserves_existing_undo() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("abc")

    assert buffer.delete_range(1, 1) == ""
    assert buffer.value == "abc"

    assert buffer.undo()
    assert buffer.value == ""
    assert not buffer.undo()


def test_delete_range_clamps_out_of_bounds() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("abc")

    assert buffer.delete_range(-5, 1) == "a"
    assert buffer.value == "bc"

    buffer.set_text("abc")
    assert buffer.delete_range(2, 100) == "c"
    assert buffer.value == "ab"


def test_replace_range_swaps_text_and_puts_cursor_at_end() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("hello world")

    removed = buffer.replace_range(6, 11, " Earth")

    assert removed == "world"
    assert buffer.value == "hello  Earth"
    assert buffer.cursor == 12


def test_replace_range_clamps_and_empty_replacement_ok() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("abc")

    assert buffer.replace_range(1, 2, "") == "b"
    assert buffer.value == "ac"
    assert buffer.cursor == 1


def test_replace_range_on_empty_buffer() -> None:
    buffer = EditorBuffer()

    assert buffer.replace_range(0, 0, "x") == ""
    assert buffer.value == "x"
    assert buffer.cursor == 1


def test_replace_range_noop_does_not_record_undo() -> None:
    buffer = EditorBuffer()
    buffer.set_text("abc")

    assert buffer.replace_range(1, 1, "") == ""
    assert buffer.value == "abc"
    assert not buffer.undo()

    assert buffer.replace_range(1, 2, "b") == "b"
    assert buffer.value == "abc"
    assert not buffer.undo()


def test_unrecorded_edits_do_not_create_undo_entries() -> None:
    buffer = EditorBuffer()

    buffer.insert_text("abc", record=False)
    buffer.delete_backward(record=False)

    assert buffer.value == "ab"
    assert not buffer.undo()
    assert buffer.value == "ab"


def test_apply_edit_records_composite_change_as_one_undo_entry() -> None:
    buffer = EditorBuffer()

    assert buffer.apply_edit(
        lambda: (
            buffer.insert_text("abc", record=False),
            buffer.delete_range(0, 1, record=False),
            buffer.insert_text("X", record=False),
        )
    )

    assert buffer.value == "Xbc"
    assert buffer.undo()
    assert buffer.value == ""
    assert not buffer.undo()


def test_word_movement_alpha_and_punctuation() -> None:
    buffer = EditorBuffer()
    buffer.set_text("alpha beta")

    buffer.move_to_end()
    assert buffer.move_word_left()
    assert buffer.cursor == 6
    assert buffer.move_word_left()
    assert buffer.cursor == 0
    assert not buffer.move_word_left()

    buffer.move_to_start()
    assert buffer.move_word_right()
    assert buffer.cursor == 5
    assert buffer.move_word_right()
    assert buffer.cursor == 10
    assert not buffer.move_word_right()


def test_word_movement_foo_bar_boundary() -> None:
    buffer = EditorBuffer()
    buffer.set_text("foo.bar")

    buffer.move_to_start()
    assert buffer.move_word_right()
    assert buffer.cursor == 3
    assert buffer.move_word_right()
    assert buffer.cursor == 4
    assert buffer.move_word_right()
    assert buffer.cursor == 7

    buffer.move_to_end()
    assert buffer.move_word_left()
    assert buffer.cursor == 4
    assert buffer.move_word_left()
    assert buffer.cursor == 3
    assert buffer.move_word_left()
    assert buffer.cursor == 0


def test_word_movement_cjk() -> None:
    buffer = EditorBuffer()
    buffer.set_text("中文测试")

    buffer.move_to_start()
    assert buffer.move_word_right()
    assert buffer.cursor == 4

    buffer.move_to_end()
    assert buffer.move_word_left()
    assert buffer.cursor == 0


def test_word_movement_emoji_cluster() -> None:
    buffer = EditorBuffer()
    buffer.set_text("a👨\u200d👩\u200d👧\u200d👦b")

    assert len(buffer) == 3

    buffer.move_to_start()
    assert buffer.move_word_right()
    assert buffer.cursor == 1
    assert buffer.move_word_right()
    assert buffer.cursor == 2
    assert buffer.move_word_right()
    assert buffer.cursor == 3


def test_word_movement_skips_spaces() -> None:
    buffer = EditorBuffer()
    buffer.set_text("   hello")

    buffer.move_to_start()
    assert buffer.move_word_right()
    assert buffer.cursor == 8
    assert not buffer.move_word_right()

    buffer.move_to_end()
    assert buffer.move_word_left()
    assert buffer.cursor == 3
    assert buffer.move_word_left()
    assert buffer.cursor == 0


def test_word_movement_newline_is_own_kind() -> None:
    buffer = EditorBuffer()
    buffer.set_text("ab\ncd")

    buffer.move_to_start()
    assert buffer.move_word_right()
    assert buffer.cursor == 2
    assert buffer.move_word_right()
    assert buffer.cursor == 3
    assert buffer.move_word_right()
    assert buffer.cursor == 5

    buffer.move_to_end()
    assert buffer.move_word_left()
    assert buffer.cursor == 3
    assert buffer.move_word_left()
    assert buffer.cursor == 2
    assert buffer.move_word_left()
    assert buffer.cursor == 0


def test_wide_characters_do_not_affect_len_or_cursor() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("中")

    assert len(buffer) == 1
    assert buffer.cursor == 1

    buffer.insert_text("🙂")
    assert len(buffer) == 2
    assert buffer.cursor == 2


def test_undo_after_replace_range_and_delete_range() -> None:
    buffer = EditorBuffer()
    buffer.insert_text("hello world")

    buffer.replace_range(6, 11, "Earth")
    assert buffer.value == "hello Earth"

    buffer.delete_range(5, 6)
    assert buffer.value == "helloEarth"

    assert buffer.undo()
    assert buffer.value == "hello Earth"
    assert buffer.undo()
    assert buffer.value == "hello world"
