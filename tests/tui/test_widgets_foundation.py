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
)
from loushang.tui.ui_parts import Button as UiButton
from loushang.tui.ui_parts.widgets import Button as WidgetButton


def test_widgets_are_reexported_from_public_modules() -> None:
    assert Button is UiButton
    assert Button is WidgetButton
    assert Choice("fast", "Fast").value == "fast"
    assert callable(IconButton)
