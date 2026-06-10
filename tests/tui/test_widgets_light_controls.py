from __future__ import annotations

from typing import Any

from loushang.tui import (
    InputEvent,
    Menu,
    MenuItem,
    RenderConstraints,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Menu as UiMenu
from loushang.tui.ui_parts import MenuItem as UiMenuItem
from loushang.tui.ui_parts.widgets import Menu as WidgetMenu
from loushang.tui.ui_parts.widgets import MenuItem as WidgetMenuItem


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_light_controls_are_reexported_from_public_modules() -> None:
    assert Menu is UiMenu
    assert Menu is WidgetMenu
    assert MenuItem is UiMenuItem
    assert MenuItem is WidgetMenuItem
    assert MenuItem("open", "Open").value == "open"


def test_menu_renders_focus_disabled_description_theme_and_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.menu.item": {"color": "white"},
            "widget.menu.focus": {"bold": True, "color": "cyan"},
            "widget.menu.disabled": {"dim": True},
            "widget.menu.description": {"color": "bright_black"},
        }
    )
    menu = Menu(
        [
            MenuItem("open", "Open", description="current"),
            MenuItem("delete", "Delete", disabled=True),
            MenuItem("quit", "Quit", icon="x"),
        ],
        theme=theme,
    )
    menu.focus()

    raw = render_lines(menu, width=40, height=4)

    assert raw[0].startswith("\x1b[1;36m> Open")
    assert "\x1b[90mcurrent" in raw[0]
    assert "\x1b[2m  Delete" in raw[1]
    assert plain_lines(menu, width=40, height=4) == (
        "> Open  current",
        "  Delete",
        "  x Quit",
    )
    assert_widths_within(render_lines(menu, width=6, height=4), 6)


def test_menu_navigation_activation_callbacks_and_space_forms() -> None:
    calls: list[str] = []
    menu = Menu(
        [
            MenuItem("open", "Open", on_select=lambda: calls.append("open")),
            MenuItem("delete", "Delete", disabled=True),
            MenuItem("quit", "Quit", on_select=lambda: "quit"),
        ]
    )
    menu.focus()

    assert menu.active_value == "open"
    assert menu.handle_input(InputEvent(kind="key", key="enter")) is True
    assert menu.handle_input(InputEvent(kind="key", key="down")) is True
    assert menu.active_value == "quit"
    assert menu.handle_input(InputEvent(kind="key", key="enter")) == "quit"
    assert menu.handle_input(InputEvent(kind="key", key="down")) is True
    assert menu.active_value == "open"
    assert menu.handle_input(InputEvent(kind="text", text=" ")) is True
    assert menu.handle_input(InputEvent(kind="key", key="space")) is True
    assert calls == ["open", "open", "open"]


def test_menu_initial_index_boundaries_empty_disabled_and_height_window() -> None:
    assert Menu(
        [
            MenuItem("one", "One"),
            MenuItem("two", "Two", disabled=True),
        ],
        active_index=99,
    ).active_value == "one"
    assert Menu([MenuItem("fallback", "Fallback")]).handle_input(InputEvent(kind="key", key="enter")) == "fallback"

    menu = Menu(
        [
            MenuItem("one", "One", disabled=True),
            MenuItem("two", "Two", disabled=True),
            MenuItem("three", "Three"),
        ],
        active_index=0,
        wrap=False,
    )
    menu.focus()

    assert menu.active_value == "three"
    assert menu.handle_input(InputEvent(kind="key", key="down")) is False
    assert menu.handle_input(InputEvent(kind="key", key="end")) is False
    assert menu.handle_input(InputEvent(kind="key", key="home")) is False
    assert menu.handle_input(InputEvent(kind="key", key="up")) is False

    assert Menu([]).handle_input(InputEvent(kind="key", key="down")) is None
    assert Menu([]).handle_input(InputEvent(kind="key", key="enter")) is None
    disabled = Menu([MenuItem("no", "No", disabled=True)])
    disabled.focus()
    assert disabled.handle_input(InputEvent(kind="key", key="down")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None

    windowed = Menu([MenuItem(str(index), f"Item {index}") for index in range(5)], active_index=4)
    windowed.focus()
    assert plain_lines(windowed, width=20, height=2) == ("  Item 3", "> Item 4")


def test_menu_description_threshold_omits_then_truncates_description() -> None:
    menu = Menu([MenuItem("build", "Build", description="compile artifacts")])

    assert plain_lines(menu, width=8, height=1) == ("  Build",)
    assert plain_lines(menu, width=13, height=1) == ("  Build  com",)
