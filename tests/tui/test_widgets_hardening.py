from __future__ import annotations

from typing import Any

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
    RadioGroup,
    RenderConstraints,
    SelectItem,
    SelectList,
    TextField,
    ThemeResolver,
    Toggle,
    strip_control_sequences,
    visible_width,
)


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_button_kind_focus_and_disabled_theme_tokens_preserve_visible_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.button.primary": {"color": "green"},
            "widget.focus": {"bold": True},
            "widget.disabled": {"dim": True},
        }
    )
    button = Button("Save", kind="primary", theme=theme)

    raw = render_lines(button, width=12)
    assert raw[0].startswith("\x1b[32m")
    assert strip_control_sequences(raw[0]) == "  [Save]"
    assert visible_width(raw[0]) == len("  [Save]")

    button.focus()
    focused = render_lines(button, width=12)
    assert focused[0].startswith("\x1b[1;32m")
    assert strip_control_sequences(focused[0]) == "> [Save]"
    assert visible_width(focused[0]) == len("> [Save]")

    disabled = Button("Save", kind="primary", disabled=True, theme=theme)
    disabled.focus()
    disabled_raw = render_lines(disabled, width=12)
    assert disabled_raw[0].startswith("\x1b[2;32m")
    assert strip_control_sequences(disabled_raw[0]) == "> [Save]"
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None


def test_button_theme_token_overrides_kind_before_focus_style() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.button.danger": {"color": "red"},
            "custom.button": {"color": "cyan"},
            "widget.focus": {"underline": True},
        }
    )
    button = Button("Delete", kind="danger", theme=theme, theme_token="custom.button", focused=True)

    raw = render_lines(button, width=16)

    assert raw[0].startswith("\x1b[4;36m")
    assert strip_control_sequences(raw[0]) == "> [Delete]"


def test_choice_widgets_apply_focus_and_disabled_theme_without_text_changes() -> None:
    theme = ThemeResolver(defaults={"widget.focus": {"bold": True}, "widget.disabled": {"dim": True}})

    checkbox = Checkbox("Enabled", checked=True, focused=True, theme=theme)
    toggle = Toggle("Auto", value=False, disabled=True, focused=True, theme=theme)
    radio = RadioGroup(
        [Choice("fast", "Fast"), Choice("slow", "Slow", disabled=True)],
        value="fast",
        theme=theme,
        focused=True,
    )

    assert render_lines(checkbox)[0].startswith("\x1b[1m")
    assert plain_lines(checkbox) == ("> [x] Enabled",)
    assert render_lines(toggle)[0].startswith("\x1b[2m")
    assert plain_lines(toggle) == ("> [off] Auto",)

    radio_lines = render_lines(radio, width=20, height=3)
    assert radio_lines[0].startswith("\x1b[1m")
    assert radio_lines[1].startswith("\x1b[2m")
    assert tuple(strip_control_sequences(line) for line in radio_lines) == ("> (x) Fast", "  ( ) Slow")


def p0a_constraint_cases() -> list[object]:
    return [
        Button("Very long label", focused=True),
        IconButton("*", label="Very long label", focused=True),
        Checkbox("Very long label", focused=True),
        Toggle("Very long label", focused=True),
        RadioGroup([Choice("a", "Very long label")], value="a", focused=True),
        TextField(label="Very long label", value="Very long value", help_text="Very long help"),
        SelectList([SelectItem("Very long label")], max_visible=1),
        Form([FormRow("name", TextField(label="Very long label", value="Very long value"))]),
        Dialog(title="Very long dialog title", body="Very long dialog body"),
        ConfirmDialog(title="Very long confirm title", body="Very long confirm body"),
    ]


def test_all_p0a_widgets_respect_small_valid_render_constraints() -> None:
    for control in p0a_constraint_cases():
        lines = render_lines(control, width=1, height=1)
        assert len(lines) <= 1
        assert_widths_within(lines, 1)


def test_all_p0a_widgets_respect_narrow_short_render_constraints() -> None:
    for control in p0a_constraint_cases():
        lines = render_lines(control, width=6, height=2)
        assert len(lines) <= 2
        assert_widths_within(lines, 6)


def test_text_field_themes_label_help_and_error_with_error_precedence() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.field.label": {"color": "cyan"},
            "widget.field.help": {"dim": True},
            "widget.error": {"color": "red"},
        }
    )
    field = TextField(label="Name", value="tower", help_text="Helpful", error="Required", theme=theme)
    field.focus()

    raw = render_lines(field, width=24, height=4)

    assert raw[0].startswith("\x1b[36m")
    assert raw[2].startswith("\x1b[31m")
    assert tuple(strip_control_sequences(line) for line in raw) == ("Name", "tower", "Required")
    assert all(visible_width(line) <= 24 for line in raw)


def test_text_field_cursor_row_stays_on_input_when_height_truncates_detail() -> None:
    field = TextField(label="Name", value="tower", help_text="Helpful")
    field.focus()

    result = field.render(RenderConstraints(width=24, max_height=2))

    assert tuple(strip_control_sequences(line.text) for line in result.lines) == ("Name", "tower")
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, len("tower"))


def test_form_themes_validation_errors_without_changing_values() -> None:
    theme = ThemeResolver(defaults={"widget.error": {"color": "red"}})
    form = Form(
        [FormRow("name", TextField(value=""), validator=lambda value: "Name required" if not value else None)],
        theme=theme,
    )

    result = form.validate()
    raw = render_lines(form, width=24, height=4)

    assert result.errors == {"name": "Name required"}
    assert raw[-1].startswith("\x1b[31m")
    assert strip_control_sequences(raw[-1]) == "Name required"
    assert form.values() == {"name": ""}
