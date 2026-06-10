from __future__ import annotations

from loushang.tui import (
    InputEvent,
    RenderConstraints,
    TextInput,
    ThemeResolver,
    Tui,
    strip_control_sequences,
)
from loushang.tui.editor_buffer import EditorBuffer
from loushang.tui.ui_parts import TextInput as ReexportedTextInput
from loushang.tui.ui_parts.text_input import TextInput as ModuleTextInput


def rendered_text(part: TextInput, *, width: int = 20, height: int = 3) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def test_text_input_imports_are_compatible() -> None:
    assert TextInput is ReexportedTextInput
    assert TextInput is ModuleTextInput


def test_text_input_delegates_editing_state_to_editor_buffer() -> None:
    field = TextInput()

    assert isinstance(field._buffer, EditorBuffer)

    assert field.handle_input(InputEvent(kind="text", text="a中e\u0301"))
    assert field.value == "a中e\u0301"
    assert field._buffer.value == "a中e\u0301"
    assert field._buffer.cursor == 3


def test_text_input_programmatic_resets_clear_edit_history() -> None:
    field = TextInput()

    assert field.handle_input(InputEvent(kind="text", text="abc"))
    field.set_text("seed")

    assert not field.undo()
    assert field.value == "seed"

    assert field.handle_input(InputEvent(kind="text", text="!"))
    field.clear()

    assert not field.undo()
    assert field.value == ""


def test_text_input_direct_edits_preserve_existing_undo_boundary() -> None:
    field = TextInput()

    field.insert_text("abc")
    field.delete_backward()

    assert field.value == "ab"
    assert not field.undo()
    assert field.value == "ab"


def test_text_input_editor_input_target_routes_high_level_text_edits() -> None:
    changes: list[str] = []
    field = TextInput(on_change=changes.append)
    target = field.editor_input_target()

    target.insert_text("ab")
    target.paste("c\nd")

    assert field.value == "abc d"
    assert changes == ["ab", "abc d"]
    assert field.undo()
    assert field.value == "ab"
    assert field.undo()
    assert field.value == ""


def test_text_input_editor_input_target_routes_destructive_edits_with_undo() -> None:
    changes: list[str] = []
    field = TextInput(on_change=changes.append)
    target = field.editor_input_target()

    target.insert_text("abc")
    target.delete_backward()

    assert field.value == "ab"
    assert changes == ["abc", "ab"]
    assert field.undo()
    assert field.value == "abc"


def test_text_input_editor_input_target_exposes_shared_editor_operations() -> None:
    field = TextInput()
    target = field.editor_input_target()

    target.insert_text("alpha beta")
    target.move_to_line_start()
    target.move_word_right()
    target.kill_to_line_end()

    assert field.value == "alpha"
    assert field.kill_ring == (" beta",)


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


def test_text_input_routes_default_redo_key() -> None:
    field = TextInput()

    assert field.handle_input(InputEvent(kind="text", text="abc"))
    assert field.handle_input(InputEvent(kind="key", key="ctrl+-"))
    assert field.value == ""

    assert field.handle_input(InputEvent(kind="key", key="alt+r"))
    assert field.value == "abc"


def test_text_input_routes_alt_u_undo_key() -> None:
    field = TextInput()

    assert field.handle_input(InputEvent(kind="text", text="abc"))
    assert field.handle_input(InputEvent(kind="key", key="alt+u"))
    assert field.value == ""


def test_text_input_routes_terminal_underscore_undo_alias() -> None:
    field = TextInput()

    assert field.handle_input(InputEvent(kind="text", text="abc"))
    assert field.handle_input(InputEvent(kind="key", key="ctrl+_"))
    assert field.value == ""


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


def test_text_input_selection_replaces_text_and_undoes_atomically() -> None:
    field = TextInput()
    field.handle_input(InputEvent(kind="text", text="你🙂a"))

    assert field.handle_input(InputEvent(kind="key", key="shift+left"))
    assert field.handle_input(InputEvent(kind="key", key="shift+left"))
    assert field.selected_range == (1, 3)

    assert field.handle_input(InputEvent(kind="text", text="x"))

    assert field.value == "你x"
    assert field.selected_range is None

    assert field.undo()

    assert field.value == "你🙂a"
    assert field.selected_range is None


def test_text_input_kill_and_yank_operate_on_selection_first() -> None:
    field = TextInput()
    field.handle_input(InputEvent(kind="text", text="alpha beta"))

    assert field.handle_input(InputEvent(kind="key", key="shift+left"))
    assert field.handle_input(InputEvent(kind="key", key="ctrl+w"))

    assert field.value == "alpha bet"
    assert field.kill_ring == ("a",)

    assert field.handle_input(InputEvent(kind="text", text="Z"))
    assert field.handle_input(InputEvent(kind="key", key="shift+left"))
    assert field.handle_input(InputEvent(kind="key", key="ctrl+y"))

    assert field.value == "alpha beta"


def test_text_input_selection_highlight_uses_editor_selection_theme_token() -> None:
    field = TextInput(
        prompt="> ",
        theme=ThemeResolver(defaults={"editor.selection": {"color": "cyan", "bold": True}}),
    )
    field.handle_input(InputEvent(kind="text", text="abc"))
    field.handle_input(InputEvent(kind="key", key="shift+left"))

    raw = rendered_text(field, width=20)[0]

    assert strip_control_sequences(raw) == "> abc"
    assert "\x1b[1;36mc\x1b[22;39m" in raw
