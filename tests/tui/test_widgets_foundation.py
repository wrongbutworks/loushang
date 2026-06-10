from __future__ import annotations

from loushang.tui import (
    Button,
    Checkbox,
    Choice,
    ConfirmDialog,
    Dialog,
    Form,
    FormRow,
    IconButton,
    InputEvent,
    InputIntent,
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
