from __future__ import annotations

import runpy
from typing import Any

import pytest

from loushang.tui import (
    RenderConstraints,
    ThemeResolver,
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


def test_toast_stack_renders_title_message_and_empty_message_rows() -> None:
    stack = ToastStack(
        (
            Toast("Saved", title="Config", kind="success", value="save", duration_ms=None),
            Toast("", title="Warning", kind="warning", value="warn", duration_ms=None),
            Toast("Plain", kind="info", value="plain", duration_ms=None),
        ),
        newest_on_top=False,
    )

    assert plain_lines(stack, width=40, height=5) == (
        "[success] Config: Saved",
        "[warning] Warning",
        "[info] Plain",
    )


def test_toast_stack_normalizes_newlines_to_single_render_line() -> None:
    stack = ToastStack(
        (
            Toast(
                "Saved\nagain",
                title="Config\rName",
                kind="success",
                value="save",
                duration_ms=None,
            ),
        ),
        newest_on_top=False,
    )

    assert plain_lines(stack, width=80, height=1) == ("[success] Config Name: Saved again",)
    assert len(render_lines(stack, width=80, height=1)) == 1


def test_toast_stack_respects_width_height_and_empty_height() -> None:
    empty = ToastStack(empty_height=1)
    assert plain_lines(empty, width=10, height=3) == ("",)
    assert plain_lines(ToastStack(empty_height=2), width=10, height=1) == ("",)
    assert plain_lines(ToastStack(), width=10, height=3) == ()

    stack = ToastStack(
        (
            Toast("Very long message", kind="info", value="a", duration_ms=None),
            Toast("Second", kind="danger", value="b", duration_ms=None),
        ),
        newest_on_top=False,
    )
    lines = render_lines(stack, width=12, height=1)

    assert plain_lines(stack, width=12, height=1) == ("[info] Very",)
    assert_widths_within(lines, 12)
    assert_widths_within(render_lines(stack, width=1, height=3), 1)


def test_toast_stack_applies_theme_tokens_and_preserves_visible_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.toast.success": {"color": "green"},
            "widget.toast.title": {"bold": True},
            "widget.toast.message": {"color": "white"},
        }
    )
    stack = ToastStack(
        (Toast("Saved", title="Config", kind="success", value="save", duration_ms=None),),
        theme=theme,
    )

    raw = render_lines(stack, width=40, height=2)

    assert len(raw) == 1
    line = raw[0]
    assert line.startswith("\x1b[32m[success]")
    assert "\x1b[1mConfig" in line
    assert "\x1b[37mSaved" in line
    assert_widths_within(raw, 40)


def test_toast_render_samples_now_once() -> None:
    clock = Clock(100, 101, 102)
    stack = ToastStack((Toast("A", value="a", created_at_ms=0, duration_ms=101),), now_ms=clock)

    assert plain_lines(stack, width=20, height=2) == ("[info] A",)
    assert clock.calls == 1


def test_toast_widgets_are_reexported_from_public_modules() -> None:
    assert Toast is UiToast
    assert Toast is WidgetToast
    assert ToastStack is UiToastStack
    assert ToastStack is WidgetToastStack
    assert ToastKind is UiToastKind
    assert ToastKind is WidgetToastKind
    assert Toast("Saved").message == "Saved"


def test_widgets_toast_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/50_widgets_toast.py", run_name="__test__")

    build_app = namespace["build_app"]
    assert callable(build_app)
    app = build_app()
    result = app.render(RenderConstraints(width=60, max_height=8))
    assert result.lines


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


def test_toast_visible_toasts_filters_expired_without_mutating() -> None:
    clock = Clock(100)
    stack = ToastStack(
        (
            Toast("Old", value="old", created_at_ms=0, duration_ms=100),
            Toast("Pinned", value="pin", created_at_ms=0, duration_ms=None),
            Toast("Fresh", value="fresh", created_at_ms=50, duration_ms=100),
        ),
        newest_on_top=False,
        now_ms=clock,
    )

    assert stack.visible_toasts() == (
        Toast("Pinned", value="pin", duration_ms=None, created_at_ms=0),
        Toast("Fresh", value="fresh", created_at_ms=50, duration_ms=100),
    )
    assert tuple(toast.value for toast in stack.all_toasts()) == ("old", "pin", "fresh")


def test_toast_expiration_boundary_is_expired() -> None:
    stack = ToastStack(
        (Toast("Boundary", value="b", created_at_ms=10, duration_ms=90),),
        now_ms=Clock(100),
    )

    assert stack.visible_toasts() == ()


def test_toast_prune_expired_mutates_and_returns_count() -> None:
    stack = ToastStack(
        (
            Toast("Old", value="old", created_at_ms=0, duration_ms=10),
            Toast("Fresh", value="fresh", created_at_ms=50, duration_ms=100),
        ),
        now_ms=Clock(100),
    )

    assert stack.prune_expired() == 1
    assert stack.all_toasts() == (
        Toast("Fresh", value="fresh", created_at_ms=50, duration_ms=100),
    )


def test_toast_expiration_operations_sample_now_once() -> None:
    visible_clock = Clock(100, 101, 102)
    stack = ToastStack(
        (Toast("A", value="a", created_at_ms=0, duration_ms=101),),
        now_ms=visible_clock,
    )

    assert tuple(toast.value for toast in stack.visible_toasts()) == ("a",)
    assert visible_clock.calls == 1

    prune_clock = Clock(100, 101, 102)
    stack = ToastStack(
        (Toast("A", value="a", created_at_ms=0, duration_ms=101),),
        now_ms=prune_clock,
    )
    assert stack.prune_expired() == 0
    assert prune_clock.calls == 1


def test_toast_ordering_and_max_visible() -> None:
    toasts = tuple(
        Toast(str(index), value=str(index), created_at_ms=index, duration_ms=None)
        for index in range(5)
    )

    newest = ToastStack(toasts, max_visible=3, newest_on_top=True, now_ms=Clock(10))
    oldest = ToastStack(toasts, max_visible=3, newest_on_top=False, now_ms=Clock(10))

    assert tuple(toast.value for toast in newest.visible_toasts()) == ("4", "3", "2")
    assert tuple(toast.value for toast in oldest.visible_toasts()) == ("0", "1", "2")
    assert ToastStack(toasts, max_visible=0).visible_toasts() == ()


def test_toast_dismiss_clear_and_non_dismissible_behavior() -> None:
    stack = ToastStack(
        (
            Toast("A", value="a"),
            Toast("B", value="b", dismissible=False),
            Toast("C", value="c"),
        )
    )

    assert stack.dismiss("missing") is False
    assert stack.dismiss("b") is False
    assert tuple(toast.value for toast in stack.all_toasts()) == ("a", "b", "c")
    assert stack.dismiss("a") is True
    assert tuple(toast.value for toast in stack.all_toasts()) == ("b", "c")
    stack.clear()
    assert stack.all_toasts() == ()


def test_toast_dismiss_oldest_skips_expired_and_non_dismissible_without_pruning() -> None:
    stack = ToastStack(
        (
            Toast("Expired", value="expired", created_at_ms=0, duration_ms=10),
            Toast(
                "Pinned",
                value="pinned",
                dismissible=False,
                created_at_ms=90,
                duration_ms=100,
            ),
            Toast("Fresh", value="fresh", created_at_ms=90, duration_ms=100),
        ),
        now_ms=Clock(100),
    )

    assert stack.dismiss_oldest() is True
    assert tuple(toast.value for toast in stack.all_toasts()) == ("expired", "pinned")
    assert stack.dismiss_oldest() is False
    assert tuple(toast.value for toast in stack.all_toasts()) == ("expired", "pinned")


def test_toast_dismiss_oldest_samples_now_once() -> None:
    clock = Clock(100, 101, 102)
    stack = ToastStack(
        (Toast("A", value="a", created_at_ms=0, duration_ms=101),),
        now_ms=clock,
    )

    assert stack.dismiss_oldest() is True
    assert clock.calls == 1


def test_toast_dismiss_oldest_only_considers_visible_window() -> None:
    toasts = tuple(
        Toast(str(index), value=str(index), created_at_ms=index, duration_ms=None)
        for index in range(5)
    )

    hidden_oldest = ToastStack(toasts, max_visible=2, newest_on_top=True)
    assert tuple(toast.value for toast in hidden_oldest.visible_toasts()) == ("4", "3")
    assert hidden_oldest.dismiss_oldest() is True
    assert tuple(toast.value for toast in hidden_oldest.all_toasts()) == (
        "0",
        "1",
        "2",
        "4",
    )

    no_visible = ToastStack(toasts, max_visible=0)
    assert no_visible.dismiss_oldest() is False
    assert tuple(toast.value for toast in no_visible.all_toasts()) == (
        "0",
        "1",
        "2",
        "3",
        "4",
    )
