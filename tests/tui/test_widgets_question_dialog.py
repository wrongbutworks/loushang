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
