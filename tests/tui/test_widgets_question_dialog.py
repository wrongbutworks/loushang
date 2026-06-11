from __future__ import annotations

import runpy
from typing import Any

import pytest

from loushang.tui import (
    InputEvent,
    QuestionDialog,
    RenderConstraints,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import QuestionDialog as UiQuestionDialog
from loushang.tui.ui_parts.widgets import QuestionDialog as WidgetQuestionDialog


def render_result(part: Any, *, width: int = 40, height: int = 8):
    return part.render(RenderConstraints(width=width, max_height=height))


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(line.text for line in render_result(part, width=width, height=height).lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def intent_tuple(intent: object) -> tuple[str, str, str]:
    return (getattr(intent, "kind", ""), getattr(intent, "text", ""), getattr(intent, "note", ""))


def intent_tuples(intents: object) -> tuple[tuple[str, str, str], ...]:
    if isinstance(intents, tuple):
        return tuple(intent_tuple(intent) for intent in intents)
    return (intent_tuple(intents),)


def test_question_dialog_is_reexported_from_public_modules() -> None:
    assert QuestionDialog is UiQuestionDialog
    assert QuestionDialog is WidgetQuestionDialog


def test_question_dialog_accepts_initial_value_but_value_is_text_area_backed() -> None:
    dialog = QuestionDialog(title="Ask", question="Details?", value="alpha\nbeta")

    assert dialog.value == "alpha\nbeta"
    with pytest.raises(AttributeError):
        dialog.value = "changed"  # type: ignore[misc]

    dialog.set_text("changed")
    assert dialog.value == "changed"

    dialog.clear()
    assert dialog.value == ""


def test_question_dialog_body_submit_returns_answer_and_close_intents() -> None:
    dialog = QuestionDialog(title="Ask", value="ship it")
    dialog.focus()

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+enter"))) == (
        ("question_submit", "ship it", ""),
        ("surface_close", "", ""),
    )


def test_question_dialog_cancel_returns_cancel_and_close_intents() -> None:
    dialog = QuestionDialog(title="Ask")
    dialog.focus()

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="escape"))) == (
        ("question_cancel", "", ""),
        ("surface_close", "", ""),
    )


def test_question_dialog_body_submit_can_keep_surface_open() -> None:
    dialog = QuestionDialog(title="Ask", value="draft", close_on_submit=False)
    dialog.focus()

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+enter"))) == (
        ("question_submit", "draft", ""),
    )


def test_question_dialog_enter_inserts_newline_and_does_not_submit() -> None:
    dialog = QuestionDialog(title="Ask", value="alpha")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="enter")) is True

    assert dialog.value == "alpha\n"


def test_question_dialog_cancel_can_keep_surface_open_and_bypasses_text_area() -> None:
    dialog = QuestionDialog(title="Ask", value="draft", close_on_cancel=False)
    dialog.focus()

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+c"))) == (
        ("question_cancel", "", ""),
    )
    assert dialog.value == "draft"


def test_question_dialog_tab_moves_between_body_and_actions_editor_target() -> None:
    dialog = QuestionDialog(title="Ask", value="")
    dialog.focus()

    assert dialog.editor_input_target() is not None
    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert dialog.editor_input_target() is None
    assert dialog.handle_input(InputEvent(kind="key", key="shift+tab")) is True
    assert dialog.editor_input_target() is not None


def test_question_dialog_action_row_defaults_to_submit_and_can_toggle_to_cancel() -> None:
    dialog = QuestionDialog(title="Ask", value="done")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="enter"))) == (
        ("question_submit", "done", ""),
        ("surface_close", "", ""),
    )

    dialog = QuestionDialog(title="Ask", value="done")
    dialog.focus()
    dialog.handle_input(InputEvent(kind="key", key="tab"))
    assert dialog.handle_input(InputEvent(kind="key", key="right")) is True
    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="space"))) == (
        ("question_cancel", "", ""),
        ("surface_close", "", ""),
    )


def test_question_dialog_action_row_printable_space_activates_active_action() -> None:
    dialog = QuestionDialog(title="Ask", value="done")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert intent_tuples(dialog.handle_input(InputEvent(kind="text", text=" "))) == (
        ("question_submit", "done", ""),
        ("surface_close", "", ""),
    )


@pytest.mark.parametrize(
    "key",
    ["enter", "shift+enter", "alt+enter", "ctrl+j", "escape", "esc", "ctrl+c", "tab", "shift+tab"],
)
def test_question_dialog_rejects_reserved_submit_keys(key: str) -> None:
    with pytest.raises(ValueError):
        QuestionDialog(title="Ask", submit_key=key)


def test_question_dialog_accepts_custom_non_reserved_submit_key() -> None:
    dialog = QuestionDialog(title="Ask", value="ok", submit_key="ctrl+s")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="ctrl+enter")) is None
    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+s"))) == (
        ("question_submit", "ok", ""),
        ("surface_close", "", ""),
    )


def test_question_dialog_required_validation_keeps_open_and_renders_error() -> None:
    dialog = QuestionDialog(title="Ask", required=True, required_message="Tell me")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="ctrl+enter")) is True

    assert "Tell me" in plain_lines(dialog, width=30, height=6)


def test_question_dialog_custom_validator_error_then_success() -> None:
    dialog = QuestionDialog(title="Ask", value="no", validator=lambda value: "Too short" if len(value) < 3 else None)
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="ctrl+enter")) is True
    assert "Too short" in plain_lines(dialog, width=30, height=6)

    dialog.set_text("yes")

    assert intent_tuples(dialog.handle_input(InputEvent(kind="key", key="ctrl+enter"))) == (
        ("question_submit", "yes", ""),
        ("surface_close", "", ""),
    )
    assert "Too short" not in plain_lines(dialog, width=30, height=6)


def test_question_dialog_renders_title_question_body_actions_and_cursor_offset() -> None:
    dialog = QuestionDialog(title="Ask", question="Why?", value="alpha\nbeta", height=3)
    dialog.focus()

    result = render_result(dialog, width=30, height=7)

    assert tuple(strip_control_sequences(line.text) for line in result.lines) == (
        "Ask",
        "Why?",
        "alpha",
        "beta",
        "",
        "  [Submit]  [Cancel]",
    )
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (3, len("beta"))


def test_question_dialog_action_row_marks_active_action_without_layout_shift() -> None:
    dialog = QuestionDialog(title="Ask", value="ok")
    dialog.focus()

    assert dialog.handle_input(InputEvent(kind="key", key="tab")) is True
    assert plain_lines(dialog, width=30, height=6)[-1] == "> [Submit]  [Cancel]"

    assert dialog.handle_input(InputEvent(kind="key", key="right")) is True
    assert plain_lines(dialog, width=30, height=6)[-1] == "  [Submit]  > [Cancel]"


def test_question_dialog_respects_width_and_height_constraints() -> None:
    dialog = QuestionDialog(
        title="Very long title",
        question="Very long question",
        value="Very long answer",
        help_text="Very long help",
    )
    dialog.focus()

    lines = render_lines(dialog, width=8, height=4)

    assert len(lines) <= 4
    assert_widths_within(lines, 8)
    assert plain_lines(dialog, width=8, height=1) == ("Very lo",)


def test_question_dialog_omits_actions_when_body_needs_final_row() -> None:
    dialog = QuestionDialog(title="Ask", question="Why?", value="answer", height=3)
    dialog.focus()

    assert plain_lines(dialog, width=20, height=3) == ("Ask", "Why?", "answer")


def test_question_dialog_omits_cursor_when_body_cannot_render() -> None:
    dialog = QuestionDialog(title="Ask", question="Why?", value="answer")
    dialog.focus()

    result = render_result(dialog, width=20, height=2)

    assert tuple(strip_control_sequences(line.text) for line in result.lines) == ("Ask", "Why?")
    assert result.cursor is None


def test_question_dialog_themes_title_question_and_action_rows() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.question.title": {"bold": True},
            "widget.question.text": {"color": "cyan"},
            "widget.question.action": {"color": "yellow"},
            "widget.question.focus": {"color": "green"},
            "widget.textArea.text": {"color": "magenta"},
        }
    )
    dialog = QuestionDialog(title="Ask", question="Why?", value="ok", theme=theme)

    raw = render_lines(dialog, width=30, height=6)

    assert raw[0].startswith("\x1b[1m")
    assert raw[1].startswith("\x1b[36m")
    assert raw[2].startswith("\x1b[35m")
    assert raw[-1].startswith("\x1b[33m")

    dialog.focus()
    dialog.handle_input(InputEvent(kind="key", key="tab"))
    focused = render_lines(dialog, width=30, height=6)
    assert focused[-1].startswith("\x1b[32m")


def test_widgets_question_dialog_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/48_widgets_question_dialog.py", run_name="__test__")

    assert callable(namespace["build_app"])
