from __future__ import annotations

import runpy
from typing import Any

import pytest

from loushang.tui import (
    Dialog,
    Form,
    FormRow,
    InputEvent,
    RenderConstraints,
    TextArea,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import TextArea as UiTextArea
from loushang.tui.ui_parts.widgets import TextArea as WidgetTextArea


def render_result(part: Any, *, width: int = 40, height: int = 8):
    return part.render(RenderConstraints(width=width, max_height=height))


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(line.text for line in render_result(part, width=width, height=height).lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_text_area_is_reexported_from_public_modules() -> None:
    assert TextArea is UiTextArea
    assert TextArea is WidgetTextArea


def test_text_area_accepts_initial_value_but_value_is_buffer_backed() -> None:
    area = TextArea(label="Notes", value="alpha\nbeta", placeholder="Type notes")

    assert area.value == "alpha\nbeta"
    with pytest.raises(AttributeError):
        area.value = "changed"  # type: ignore[misc]


def test_text_area_programmatic_text_methods_preserve_newlines_and_clear_undo() -> None:
    area = TextArea(value="draft")

    area.set_text("one\ntwo")

    assert area.value == "one\ntwo"
    assert area.undo() is False

    area.clear()

    assert area.value == ""
    assert area.undo() is False


def test_text_area_handles_text_paste_enter_submit_and_escape() -> None:
    submits: list[str] = []
    escapes: list[str] = []
    changes: list[str] = []
    area = TextArea(on_submit=submits.append, on_escape=lambda: escapes.append("escape"), on_change=changes.append)

    assert area.handle_input(InputEvent(kind="text", text="alpha\nbeta")) is True
    assert area.value == "alpha\nbeta"

    assert area.handle_input(InputEvent(kind="key", key="enter")) is True
    assert area.value == "alpha\nbeta\n"
    assert submits == []

    assert area.handle_input(InputEvent(kind="paste", text="gamma\ndelta")) is True
    assert area.value == "alpha\nbeta\ngamma\ndelta"

    assert area.handle_input(
        InputEvent(kind="key", key="ctrl+enter"),
        keybindings={"tui.input.submit": ("ctrl+enter",)},
    ) is True
    assert submits == ["alpha\nbeta\ngamma\ndelta"]

    assert area.handle_input(InputEvent(kind="key", key="escape")) is True
    assert escapes == ["escape"]
    assert changes == ["alpha\nbeta", "alpha\nbeta\n", "alpha\nbeta\ngamma\ndelta"]


def test_text_area_leaves_up_and_down_available_to_parent_containers() -> None:
    area = TextArea(value="alpha\nbeta")

    assert area.handle_input(InputEvent(kind="key", key="up")) is False
    assert area.handle_input(InputEvent(kind="key", key="down")) is False


def test_text_area_editor_target_preserves_multiline_edits_and_undo() -> None:
    changes: list[str] = []
    area = TextArea(on_change=changes.append)
    target = area.editor_input_target()

    target.insert_text("alpha")
    target.paste("\nbeta")
    target.delete_backward()

    assert area.value == "alpha\nbet"
    assert changes == ["alpha", "alpha\nbeta", "alpha\nbet"]
    assert area.undo() is True
    assert area.value == "alpha\nbeta"


def test_text_area_line_boundaries_kill_and_delete_respect_current_logical_line() -> None:
    area = TextArea(value="alpha\nbeta")
    target = area.editor_input_target()

    target.move_to_line_start()
    target.delete_backward()
    assert area.value == "alphabeta"
    assert area.undo() is True
    assert area.value == "alpha\nbeta"

    target.move_to_line_end()
    target.kill_to_line_start()
    assert area.value == "alpha\n"
    assert area.kill_ring == ("beta",)


def test_text_area_multiline_selection_replaces_atomically() -> None:
    area = TextArea(value="ab\ncd")
    target = area.editor_input_target()

    target.select_char_left()
    target.select_char_left()
    target.select_char_left()
    assert area.selected_range == (2, 5)

    target.insert_text("X")

    assert area.value == "abX"
    assert area.selected_range is None
    assert area.undo() is True
    assert area.value == "ab\ncd"


def test_text_area_renders_label_body_placeholder_and_detail_with_height_precedence() -> None:
    area = TextArea(label="Notes", placeholder="Type notes", error="Required", height=4)

    assert plain_lines(area, width=20, height=5) == ("Notes", "Type notes", "", "", "Required")
    assert plain_lines(area, width=20, height=2) == ("Notes", "Type notes")


def test_text_area_error_takes_precedence_over_help_and_visible_width_is_constrained() -> None:
    area = TextArea(label="Very long label", value="Very long value", help_text="Helpful", error="Required", height=2)
    area.editor_input_target().move_to_line_start()

    lines = render_lines(area, width=8, height=4)

    assert plain_lines(area, width=8, height=4) == ("Very lo", "Very lo", "", "Require")
    assert_widths_within(lines, 8)


def test_text_area_cursor_maps_to_body_row_after_label() -> None:
    area = TextArea(label="Notes", value="ab\ncd", height=4)

    result = render_result(area, width=20, height=6)

    assert plain_lines(area, width=20, height=6)[:3] == ("Notes", "ab", "cd")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (2, 2)


def test_text_area_placeholder_does_not_move_cursor() -> None:
    area = TextArea(placeholder="Type notes", height=3)

    result = render_result(area, width=20, height=3)

    assert plain_lines(area, width=20, height=3) == ("Type notes", "", "")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (0, 0)


def test_text_area_scrolls_vertically_to_keep_cursor_visible() -> None:
    area = TextArea(value="one\ntwo\nthree\nfour", height=2)

    result = render_result(area, width=20, height=2)

    assert plain_lines(area, width=20, height=2) == ("three", "four")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, len("four"))


def test_text_area_scrolls_horizontally_across_visible_body_rows() -> None:
    area = TextArea(value="abcdef\n123456", height=2)

    result = render_result(area, width=4, height=2)

    assert plain_lines(area, width=4, height=2) == ("def", "456")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, 3)


def test_text_area_selection_highlight_uses_editor_selection_theme_token() -> None:
    area = TextArea(
        value="ab\ncd",
        theme=ThemeResolver(defaults={"editor.selection": {"color": "cyan", "bold": True}}),
    )
    target = area.editor_input_target()
    target.select_char_left()

    raw = render_lines(area, width=20, height=3)[1]

    assert strip_control_sequences(raw) == "cd"
    assert "\x1b[1;36md\x1b[22;39m" in raw


def test_text_area_integrates_with_form_values_and_editor_target() -> None:
    area = TextArea(value="")
    form = Form([FormRow("notes", area)])
    form.focus()

    assert form.handle_input(InputEvent(kind="text", text="one\ntwo")) is True
    assert form.values() == {"notes": "one\ntwo"}

    target = form.editor_input_target()
    assert target is not None
    target.insert_text("\nthree")

    assert area.value == "one\ntwo\nthree"


def test_text_area_dialog_delegates_active_editor_target() -> None:
    area = TextArea(value="")
    form = Form([FormRow("notes", area)])
    dialog = Dialog(title="Edit notes", body=form)
    dialog.focus()

    target = dialog.editor_input_target()
    assert target is not None
    target.insert_text("alpha\nbeta")

    assert area.value == "alpha\nbeta"


def test_widgets_textarea_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/47_widgets_textarea.py", run_name="__test__")

    assert callable(namespace["build_app"])
