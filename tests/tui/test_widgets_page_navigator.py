from __future__ import annotations

from typing import Any

from loushang.tui import (
    InputEvent,
    PageNavigation,
    PageNavigationError,
    PageNavigator,
    RenderConstraints,
    strip_control_sequences,
)
from loushang.tui.ui_parts import PageNavigator as UiPageNavigator
from loushang.tui.ui_parts.widgets import PageNavigator as WidgetPageNavigator


def plain_lines(part: Any, *, width: int = 80, height: int = 3) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)


def test_page_navigator_is_reexported_from_public_modules() -> None:
    assert PageNavigator is UiPageNavigator
    assert PageNavigator is WidgetPageNavigator


def test_page_navigator_renders_current_page_total_and_detail() -> None:
    navigator = PageNavigator(current_page=3, total_pages=42, detail_text="Row 41/800")

    assert plain_lines(navigator, width=80) == ("  Go to page: [3   ] / 42    Row 41/800",)


def test_page_navigator_focus_selects_page_and_submits_clamped_navigation() -> None:
    navigator = PageNavigator(current_page=3, total_pages=42)

    navigator.focus()
    assert plain_lines(navigator, width=80) == ("> Go to page: [3   ] / 42",)
    assert navigator.handle_input(InputEvent(kind="text", text="99")) is True
    result = navigator.handle_input(InputEvent(kind="key", key="enter"))

    assert result == PageNavigation(page=42, previous_page=3, raw_value="99")
    assert navigator.current_page == 42
    assert navigator.value == "42"
    assert navigator.error == ""


def test_page_navigator_invalid_submit_preserves_page_and_focuses_error() -> None:
    navigator = PageNavigator(current_page=3, total_pages=42, focused=True)

    assert navigator.handle_input(InputEvent(kind="text", text="abc")) is True
    result = navigator.handle_input(InputEvent(kind="key", key="enter"))

    assert result == PageNavigationError(raw_value="abc", message="Invalid page")
    assert navigator.current_page == 3
    assert navigator.value == "abc"
    assert navigator.error == "Invalid page"
    assert navigator.focused is True


def test_page_navigator_sync_does_not_clobber_focused_input() -> None:
    navigator = PageNavigator(current_page=1, total_pages=10)

    navigator.set_page(4, total_pages=12)
    assert navigator.current_page == 4
    assert navigator.total_pages == 12
    assert navigator.value == "4"

    navigator.focus()
    assert navigator.handle_input(InputEvent(kind="text", text="9")) is True
    navigator.set_page(5, total_pages=20)

    assert navigator.current_page == 5
    assert navigator.total_pages == 20
    assert navigator.value == "9"
    assert plain_lines(navigator, width=80) == ("> Go to page: [9   ] / 20",)


def test_page_navigator_cursor_stays_within_truncated_render_line() -> None:
    navigator = PageNavigator(current_page=1, total_pages=1234, detail_text="Row 1000/2000", focused=True)

    result = navigator.render(RenderConstraints(width=24, max_height=1))

    assert result.cursor is None or result.cursor.column <= result.lines[result.cursor.row].width
