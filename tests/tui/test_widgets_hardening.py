from __future__ import annotations

from typing import Any

from loushang.tui import (
    Button,
    InputEvent,
    RenderConstraints,
    ThemeResolver,
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
