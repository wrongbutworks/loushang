from __future__ import annotations

import runpy

from loushang.tui import (
    Button,
    Checkbox,
    Choice,
    ConfirmDialog,
    CursorDeclaration,
    Dialog,
    Form,
    FormRow,
    IconButton,
    InputEvent,
    RadioGroup,
    RenderConstraints,
    RenderLine,
    RenderResult,
    SelectItem,
    SelectList,
    TextField,
    Toggle,
    strip_control_sequences,
)
from loushang.tui.ui_parts import Button as UiButton
from loushang.tui.ui_parts.widgets import Button as WidgetButton


def test_widgets_are_reexported_from_public_modules() -> None:
    assert Button is UiButton
    assert Button is WidgetButton
    assert Choice("fast", "Fast").value == "fast"
    assert callable(IconButton)


def rendered_text(part: object, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text) for line in result.lines)


def intent_tuple(intent: object) -> tuple[str, str, str]:
    return (
        getattr(intent, "kind", ""),
        getattr(intent, "text", ""),
        getattr(intent, "note", ""),
    )


def intent_tuples(intents: tuple[object, ...]) -> tuple[tuple[str, str, str], ...]:
    return tuple(intent_tuple(intent) for intent in intents)


def test_button_activates_from_enter_and_space_without_layout_shift() -> None:
    calls: list[str] = []
    button = Button("Save", on_press=lambda: calls.append("save"))

    assert rendered_text(button, width=12) == ("  [Save]",)
    button.focus()
    assert rendered_text(button, width=12) == ("> [Save]",)
    assert button.handle_input(InputEvent(kind="key", key="enter")) is True
    assert button.handle_input(InputEvent(kind="text", text=" ")) is True
    assert calls == ["save", "save"]


def test_button_returns_callback_value_and_ignores_disabled_activation() -> None:
    button = Button("Delete", disabled=True, on_press=lambda: "deleted")

    assert button.handle_input(InputEvent(kind="key", key="enter")) is None

    active = Button("Delete", on_press=lambda: "deleted")
    assert active.handle_input(InputEvent(kind="key", key="space")) == "deleted"


def test_checkbox_toggles_from_enter_and_printable_space() -> None:
    seen: list[bool] = []
    checkbox = Checkbox("Enable cache", checked=False, on_change=seen.append)

    assert rendered_text(checkbox) == ("  [ ] Enable cache",)
    checkbox.focus()
    assert checkbox.handle_input(InputEvent(kind="key", key="enter")) is True
    assert checkbox.checked is True
    assert rendered_text(checkbox) == ("> [x] Enable cache",)
    assert checkbox.handle_input(InputEvent(kind="text", text=" ")) is True
    assert checkbox.checked is False
    assert seen == [True, False]


def test_toggle_renders_distinct_state_and_ignores_disabled_activation() -> None:
    toggle = Toggle("Auto approve", value=False)

    assert rendered_text(toggle) == ("  [off] Auto approve",)
    assert toggle.handle_input(InputEvent(kind="key", key="space")) is True
    assert toggle.value is True
    assert rendered_text(toggle) == ("  [on ] Auto approve",)

    disabled = Toggle("Auto approve", value=False, disabled=True)
    assert disabled.handle_input(InputEvent(kind="text", text=" ")) is None
    assert disabled.value is False


def test_radio_group_moves_active_option_and_commits_selection() -> None:
    seen: list[str] = []
    group = RadioGroup(
        [Choice("fast", "Fast"), Choice("safe", "Safe"), Choice("slow", "Slow", disabled=True)],
        value="fast",
        on_change=seen.append,
    )

    group.focus()
    assert rendered_text(group, width=20, height=4)[:2] == ("> (x) Fast", "  ( ) Safe")
    assert group.handle_input(InputEvent(kind="key", key="down")) is True
    assert group.value == "fast"
    assert rendered_text(group, width=20, height=4)[:2] == ("  (x) Fast", "> ( ) Safe")
    assert group.handle_input(InputEvent(kind="key", key="enter")) is True
    assert group.value == "safe"
    assert seen == ["safe"]
    assert group.handle_input(InputEvent(kind="key", key="down")) is True
    assert group.active_value == "fast"


def test_text_field_delegates_editing_and_cursor_to_text_input() -> None:
    field = TextField(label="Name", value="tower", help_text="Required")
    field.focus()

    assert field.handle_input(InputEvent(kind="text", text="!")) is True
    assert field.value == "tower!"

    result = field.render(RenderConstraints(width=24, max_height=4))
    lines = tuple(strip_control_sequences(line.text) for line in result.lines)
    assert lines == ("Name", "tower!", "Required")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, len("tower!"))


def test_text_field_editor_input_target_preserves_text_input_undo() -> None:
    field = TextField(value="")
    target = field.editor_input_target()

    target.insert_text("abc")
    target.delete_backward()

    assert field.value == "ab"
    assert field.undo()
    assert field.value == "abc"


def test_text_field_inserts_printable_space_as_text() -> None:
    field = TextField(value="a")

    assert field.handle_input(InputEvent(kind="text", text=" ")) is True

    assert field.value == "a "


def test_form_render_exposes_active_child_cursor() -> None:
    form = Form([FormRow("name", TextField(label="Name", value="tower")), FormRow("enabled", Checkbox("Enabled"))])
    form.focus()

    result = form.render(RenderConstraints(width=40, max_height=8))

    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, len("tower"))


def test_select_list_delegates_navigation_and_selection_without_default_escape_close() -> None:
    select = SelectList([SelectItem("Kimi"), SelectItem("Qwen")], max_visible=2)

    assert select.handle_input(InputEvent(kind="key", key="down")) is True
    assert select.selected_value == "Qwen"
    assert intent_tuple(select.handle_input(InputEvent(kind="key", key="enter"))) == ("select", "Qwen", "")
    assert select.handle_input(InputEvent(kind="key", key="escape")) is None


def test_select_list_can_emit_surface_close_for_popup_usage() -> None:
    select = SelectList([SelectItem("Kimi")], close_on_escape=True)

    assert intent_tuple(select.handle_input(InputEvent(kind="key", key="escape"))) == ("surface_close", "", "")


def test_select_list_only_shows_focus_marker_when_focused() -> None:
    select = SelectList([SelectItem("Kimi"), SelectItem("Qwen")], max_visible=2)

    assert rendered_text(select, width=20, height=2) == ("  Kimi", "  Qwen")

    select.focus()
    assert rendered_text(select, width=20, height=2) == ("> Kimi", "  Qwen")

    select.blur()
    assert rendered_text(select, width=20, height=2) == ("  Kimi", "  Qwen")


def test_form_tabs_between_focusable_rows_and_delegates_input() -> None:
    name = TextField(value="")
    enabled = Checkbox("Enabled")
    form = Form([FormRow("name", name), FormRow("enabled", enabled)])

    form.focus()
    assert name.focused is True
    assert form.handle_input(InputEvent(kind="text", text="a")) is True
    assert name.value == "a"
    assert form.handle_input(InputEvent(kind="key", key="tab")) is True
    assert enabled.focused is True
    assert form.handle_input(InputEvent(kind="text", text=" ")) is True
    assert enabled.checked is True


def test_form_validation_uses_field_ids_and_value_getters() -> None:
    name = TextField(value="")
    form = Form(
        [
            FormRow("name", name, validator=lambda value: "Name required" if not value else None),
            FormRow("enabled", Checkbox("Enabled", checked=True), value_getter=lambda control: control.checked),
        ]
    )

    result = form.validate()

    assert result.valid is False
    assert result.errors == {"name": "Name required"}
    assert form.values() == {"name": "", "enabled": True}


def test_form_exposes_active_editable_child_target() -> None:
    field = TextField(value="")
    form = Form([FormRow("name", field), FormRow("enabled", Checkbox("Enabled"))])
    form.focus()

    target = form.editor_input_target()
    assert target is not None
    target.insert_text("abc")
    assert field.value == "abc"

    form.focus_next()
    assert form.editor_input_target() is None


def test_confirm_dialog_returns_confirm_and_close_intents_by_default() -> None:
    dialog = ConfirmDialog(title="Delete session?")

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="enter"))) == (
        ("dialog_confirm", "", ""),
        ("surface_close", "", ""),
    )
    assert intent_tuple(dialog.handle_input(InputEvent(kind="key", key="escape"))) == ("dialog_cancel", "", "")


def test_confirm_dialog_can_keep_open_after_confirm() -> None:
    dialog = ConfirmDialog(title="Validate", close_on_confirm=False)

    assert intent_tuple(dialog.handle_input(InputEvent(kind="key", key="enter"))) == ("dialog_confirm", "", "")


class RecordingBody:
    def __init__(self) -> None:
        self.focused = False
        self.events: list[str] = []

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: InputEvent) -> object:
        if event.kind == "key":
            self.events.append(event.key)
        return True

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([RenderLine("body")], constraints=constraints)


def test_dialog_cancels_before_body_handles_cancel_keys() -> None:
    body = RecordingBody()
    dialog = Dialog(title="Edit", body=body)
    dialog.focus()

    assert intent_tuple(dialog.handle_input(InputEvent(kind="key", key="escape"))) == ("dialog_cancel", "", "")
    assert intent_tuple(dialog.handle_input(InputEvent(kind="key", key="ctrl+c"))) == ("dialog_cancel", "", "")
    assert body.events == []


def test_dialog_tabs_from_form_edge_to_actions_and_delegates_editor_target() -> None:
    field = TextField(value="")
    form = Form([FormRow("name", field)])
    dialog = ConfirmDialog(title="Edit", body=form)
    dialog.focus()

    target = dialog.editor_input_target()
    assert target is not None
    target.insert_text("abc")
    assert field.value == "abc"

    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert dialog.editor_input_target() is None
    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="enter"))) == (
        ("dialog_confirm", "", ""),
        ("surface_close", "", ""),
    )


def test_widgets_foundation_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/43_widgets_foundation.py", run_name="__test__")

    build_app = namespace["build_app"]
    assert callable(build_app)
    app = build_app()
    result = app.render(RenderConstraints(width=80, max_height=20))
    assert result.lines


def test_widgets_foundation_example_offsets_name_cursor_after_header() -> None:
    namespace = runpy.run_path("examples/tui/43_widgets_foundation.py", run_name="__test__")

    app = namespace["build_app"]()
    result = app.render(RenderConstraints(width=80, max_height=20))

    assert result.cursor == CursorDeclaration(row=3, column=len("tower"))
