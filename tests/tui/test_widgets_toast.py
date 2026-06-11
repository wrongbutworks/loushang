from __future__ import annotations

from typing import Any

import pytest

from loushang.tui import (
    RenderConstraints,
    Toast,
    ToastKind,
    ToastStack,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Toast as UiToast
from loushang.tui.ui_parts import ToastKind as UiToastKind
from loushang.tui.ui_parts import ToastStack as UiToastStack
from loushang.tui.ui_parts.widgets import Toast as WidgetToast
from loushang.tui.ui_parts.widgets import ToastKind as WidgetToastKind
from loushang.tui.ui_parts.widgets import ToastStack as WidgetToastStack


class Clock:
    def __init__(self, *values: int) -> None:
        self.values = list(values) or [0]
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)

    def set(self, value: int) -> None:
        self.values = [value]


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_toast_widgets_are_reexported_from_public_modules() -> None:
    assert Toast is UiToast
    assert Toast is WidgetToast
    assert ToastStack is UiToastStack
    assert ToastStack is WidgetToastStack
    assert ToastKind is UiToastKind
    assert ToastKind is WidgetToastKind
    assert Toast("Saved").message == "Saved"


def test_toast_stack_normalizes_generated_values_and_timestamps() -> None:
    clock = Clock(100)
    stack = ToastStack(
        (
            Toast("Saved"),
            Toast("Synced", value="sync", created_at_ms=50),
        ),
        now_ms=clock,
    )

    assert stack.all_toasts() == (
        Toast("Saved", value="toast-1", created_at_ms=100),
        Toast("Synced", value="sync", created_at_ms=50),
    )
    assert clock.calls == 1

    assert stack.push("Queued", kind="success", title="Job") == "toast-2"
    assert stack.all_toasts()[-1] == Toast(
        "Queued",
        title="Job",
        kind="success",
        value="toast-2",
        created_at_ms=100,
    )


def test_toast_stack_rejects_duplicate_values_invalid_kind_and_negative_duration() -> None:
    with pytest.raises(ValueError):
        ToastStack((Toast("One", value="dup"), Toast("Two", value="dup")))

    with pytest.raises(ValueError):
        ToastStack((Toast("Bad", kind="unknown"),))  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        ToastStack((Toast("Bad", duration_ms=-1),))


def test_toast_stack_push_applies_toast_overrides_and_rejects_message_override_for_strings() -> None:
    stack = ToastStack(now_ms=Clock(5))

    value = stack.push(Toast("Saved", value="save"), kind="success", title="Config")

    assert value == "save"
    assert stack.all_toasts() == (
        Toast("Saved", title="Config", kind="success", value="save", created_at_ms=5),
    )

    with pytest.raises(TypeError):
        stack.push("Saved", message="Other")  # type: ignore[call-arg]
