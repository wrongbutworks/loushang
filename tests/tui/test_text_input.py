from __future__ import annotations

from loushang.tui import InputEvent, RenderConstraints, TextInput, Tui
from loushang.tui.ui_parts import TextInput as ReexportedTextInput
from loushang.tui.ui_parts.text_input import TextInput as ModuleTextInput


def rendered_text(part: TextInput, *, width: int = 20, height: int = 3) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def test_text_input_imports_are_compatible() -> None:
    assert TextInput is ReexportedTextInput
    assert TextInput is ModuleTextInput


def test_text_input_can_be_focused_as_a_standalone_overlay() -> None:
    tui = Tui()
    field = TextInput(prompt="Search: ")

    tui.show_overlay(field)

    assert field.focused is True
    assert tui.handle_input(InputEvent(kind="text", text="abc")) == ()
    assert field.value == "abc"


def test_text_input_edits_single_line_text_and_maps_cursor() -> None:
    field = TextInput(prompt="Name: ")

    field.insert_text("abc")
    field.move_left()
    field.delete_backward()
    result = field.render(RenderConstraints(width=20, max_height=3))

    assert field.value == "ac"
    assert tuple(line.text for line in result.lines) == ("Name: ac",)
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (0, len("Name: a"))


def test_text_input_scrolls_horizontally_to_keep_cursor_visible() -> None:
    field = TextInput(prompt="> ")

    field.insert_text("abcdef")
    result = field.render(RenderConstraints(width=8, max_height=3))

    assert tuple(line.text for line in result.lines) == ("> bcdef",)
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (0, 7)


def test_text_input_placeholder_does_not_move_cursor() -> None:
    field = TextInput(prompt="Search: ", placeholder="type to filter")

    result = field.render(RenderConstraints(width=24, max_height=3))

    assert rendered_text(field, width=24) == ("Search: type to filter",)
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (0, len("Search: "))


def test_text_input_handles_input_events_and_callbacks() -> None:
    submits: list[str] = []
    escapes: list[str] = []
    changes: list[str] = []
    field = TextInput(
        prompt="> ",
        on_submit=submits.append,
        on_escape=lambda: escapes.append("escape"),
        on_change=changes.append,
    )

    assert field.handle_input(InputEvent(kind="text", text="ab"))
    assert field.handle_input(InputEvent(kind="key", key="left"))
    assert field.handle_input(InputEvent(kind="text", text="X"))
    assert field.handle_input(InputEvent(kind="paste", text="c\nd"))
    assert field.value == "aXc db"

    assert field.handle_input(InputEvent(kind="key", key="enter"))
    assert submits == ["aXc db"]
    assert field.handle_input(InputEvent(kind="key", key="escape"))
    assert escapes == ["escape"]
    assert changes == ["ab", "aXb", "aXc db"]


def test_text_input_handles_word_kill_yank_and_undo() -> None:
    field = TextInput()
    field.handle_input(InputEvent(kind="text", text="alpha beta"))

    assert field.handle_input(InputEvent(kind="key", key="ctrl+w"))
    assert field.value == "alpha "

    assert field.handle_input(InputEvent(kind="key", key="ctrl+y"))
    assert field.value == "alpha beta"

    assert field.handle_input(InputEvent(kind="key", key="ctrl+-"))
    assert field.value == "alpha "


def test_text_input_handles_line_editing_keys() -> None:
    field = TextInput()
    field.handle_input(InputEvent(kind="text", text="alpha beta"))

    assert field.handle_input(InputEvent(kind="key", key="ctrl+a"))
    assert field.handle_input(InputEvent(kind="key", key="alt+f"))
    assert field.handle_input(InputEvent(kind="key", key="delete"))
    assert field.value == "alphabeta"

    assert field.handle_input(InputEvent(kind="key", key="ctrl+e"))
    assert field.handle_input(InputEvent(kind="key", key="ctrl+u"))
    assert field.value == ""
