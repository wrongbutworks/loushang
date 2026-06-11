from __future__ import annotations

from typing import Any

import pytest

from loushang.tui import (
    RenderConstraints,
    TextArea,
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
