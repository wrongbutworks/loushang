from __future__ import annotations

import runpy
from typing import Any

from loushang.tui import (
    InputEvent,
    Menu,
    MenuItem,
    RenderConstraints,
    Spinner,
    TabItem,
    Tabs,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Menu as UiMenu
from loushang.tui.ui_parts import MenuItem as UiMenuItem
from loushang.tui.ui_parts import Spinner as UiSpinner
from loushang.tui.ui_parts import TabItem as UiTabItem
from loushang.tui.ui_parts import Tabs as UiTabs
from loushang.tui.ui_parts.widgets import Menu as WidgetMenu
from loushang.tui.ui_parts.widgets import MenuItem as WidgetMenuItem
from loushang.tui.ui_parts.widgets import Spinner as WidgetSpinner
from loushang.tui.ui_parts.widgets import TabItem as WidgetTabItem
from loushang.tui.ui_parts.widgets import Tabs as WidgetTabs
from tests.tui.widget_example_playback import play_example


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
    assert Spinner is UiSpinner
    assert Spinner is WidgetSpinner
    assert Tabs is UiTabs
    assert Tabs is WidgetTabs
    assert TabItem is UiTabItem
    assert TabItem is WidgetTabItem
    assert MenuItem("open", "Open").value == "open"
    assert Spinner(label="Loading").label == "Loading"


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


def test_tabs_normalize_value_render_theme_and_width() -> None:
    changes: list[str] = []
    theme = ThemeResolver(
        defaults={
            "widget.tabs.tab": {"color": "white"},
            "widget.tabs.selected": {"color": "green"},
            "widget.tabs.focus": {"bold": True, "color": "cyan"},
            "widget.tabs.disabled": {"dim": True},
        }
    )
    tabs = Tabs(
        [
            TabItem("overview", "Overview"),
            TabItem("logs", "Logs", badge="3"),
            TabItem("settings", "Settings", disabled=True),
        ],
        value="missing",
        on_change=lambda value: changes.append(value),
        theme=theme,
    )

    assert tabs.value == "overview"
    assert tabs.selected_value == "overview"
    assert changes == []
    assert plain_lines(tabs, width=60, height=1) == ("* [Overview]    [Logs 3]    [Settings]",)

    tabs.focus()
    raw = render_lines(tabs, width=60, height=1)[0]
    assert raw.startswith("\x1b[1;36m> [Overview]")
    assert "\x1b[2m  [Settings]" in raw
    assert_widths_within(render_lines(tabs, width=10, height=1), 10)


def test_tabs_level_tokens_fallback_to_legacy_tab_token() -> None:
    theme = ThemeResolver(defaults={"widget.tabs.tab": {"color": "red"}})
    tabs = Tabs([TabItem("one", "One"), TabItem("two", "Two")], theme=theme)

    raw = render_lines(tabs, width=40, height=1)[0]

    assert "\x1b[31m  [Two]" in raw


def test_tabs_navigation_changes_value_callbacks_and_activation_forms() -> None:
    calls: list[str] = []

    def record_change(value: str) -> str:
        calls.append(value)
        return f"changed:{value}"

    tabs = Tabs(
        [
            TabItem("overview", "Overview"),
            TabItem("disabled", "Disabled", disabled=True),
            TabItem("logs", "Logs"),
        ],
        on_change=record_change,
    )
    tabs.focus()

    assert tabs.handle_input(InputEvent(kind="key", key="right")) == "changed:logs"
    assert tabs.value == "logs"
    assert calls == ["logs"]
    assert tabs.handle_input(InputEvent(kind="key", key="enter")) == "logs"
    assert tabs.handle_input(InputEvent(kind="text", text=" ")) == "logs"
    assert tabs.handle_input(InputEvent(kind="key", key="space")) == "logs"
    assert tabs.handle_input(InputEvent(kind="key", key="right")) == "changed:overview"
    assert tabs.value == "overview"
    assert calls == ["logs", "overview"]


def test_tabs_boundaries_disabled_last_value_and_empty_all_disabled_semantics() -> None:
    assert Tabs(
        [
            TabItem("one", "One"),
            TabItem("two", "Two", disabled=True),
            TabItem("three", "Three"),
        ],
        value="two",
    ).value == "three"

    jumps = Tabs(
        [
            TabItem("one", "One"),
            TabItem("two", "Two"),
            TabItem("three", "Three"),
        ],
        value="one",
        wrap=False,
    )
    assert jumps.handle_input(InputEvent(kind="key", key="end")) is True
    assert jumps.value == "three"
    assert jumps.handle_input(InputEvent(kind="key", key="home")) is True
    assert jumps.value == "one"

    tabs = Tabs(
        [
            TabItem("one", "One"),
            TabItem("two", "Two", disabled=True),
        ],
        value="two",
        wrap=False,
    )
    tabs.focus()

    assert tabs.value == "one"
    assert tabs.handle_input(InputEvent(kind="key", key="left")) is False
    assert tabs.handle_input(InputEvent(kind="key", key="home")) is False
    assert tabs.handle_input(InputEvent(kind="key", key="end")) is False
    assert tabs.handle_input(InputEvent(kind="key", key="right")) is False

    assert Tabs([]).value == ""
    assert Tabs([]).handle_input(InputEvent(kind="key", key="right")) is None
    disabled = Tabs([TabItem("no", "No", disabled=True)])
    disabled.focus()
    assert disabled.value == ""
    assert disabled.handle_input(InputEvent(kind="key", key="right")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None


def test_spinner_renders_frame_modulo_label_empty_frames_and_width() -> None:
    assert plain_lines(Spinner(label="Loading", frame=5), width=20, height=1) == ("/ Loading",)
    assert plain_lines(Spinner(label="", frame=2), width=20, height=1) == ("-",)
    assert plain_lines(Spinner(label="Waiting", frames=()), width=20, height=1) == ("Waiting",)
    assert plain_lines(Spinner(label="", frames=()), width=20, height=1) == ("",)
    assert_widths_within(render_lines(Spinner(label="Very long loading label"), width=8, height=1), 8)
    assert not hasattr(Spinner(label="Loading"), "handle_input")
    assert not hasattr(Spinner(label="Loading"), "focus")


def test_spinner_applies_theme_tokens_without_width_growth() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.spinner.frame": {"color": "cyan"},
            "widget.spinner.label": {"bold": True},
        }
    )
    raw = render_lines(Spinner(label="Loading", frame=0, theme=theme), width=20, height=1)[0]

    assert raw.startswith("\x1b[36m|\x1b[39m")
    assert "\x1b[1mLoading" in raw
    assert strip_control_sequences(raw) == "| Loading"
    assert visible_width(raw) == len("| Loading")


def test_widgets_light_controls_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/45_widgets_light_controls.py", run_name="__test__")

    build_app = namespace["build_app"]
    assert callable(build_app)
    app = build_app()
    result = app.render(RenderConstraints(width=80, max_height=20))
    assert result.lines


def test_widgets_light_controls_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/45_widgets_light_controls.py",
        events=(
            ("right", InputEvent(kind="key", key="right")),
            ("tab", InputEvent(kind="key", key="tab")),
            ("down", InputEvent(kind="key", key="down")),
            ("enter", InputEvent(kind="key", key="enter")),
        ),
    )

    assert frames[0].lines[:12] == (
        "View Switcher",
        "",
        "Views         > [Overview]    [Logs 3]    [Settings]",
        "Activity      | Syncing",
        "",
        "Actions",
        "                Open  current view",
        "                Refresh",
        "                Archive  disabled",
        "",
        "Status        Ready",
        "",
    )
    assert "Views           [Overview]  > [Logs 3]    [Settings]" in frames[1].lines
    assert "              > Open  current view" in frames[2].lines
    assert "              > Refresh" in frames[3].lines
    assert "Status        Refreshed" in frames[4].lines
    assert sum(line.count(">") for line in frames[0].lines) == 1
    assert sum(line.count(">") for line in frames[2].lines) == 1


def test_widgets_light_controls_example_highlights_active_region() -> None:
    namespace = runpy.run_path("examples/tui/45_widgets_light_controls.py", run_name="__test__")
    tui = namespace["build_app"]()

    initial = tui.render(RenderConstraints(width=80, max_height=20))
    initial_lines = tuple(line.text for line in initial.lines)

    assert "\x1b[1;36m> [Overview]" in initial_lines[2]
    assert "\x1b[1;36m> Open" not in initial_lines[6]

    tui.handle_input(InputEvent(kind="key", key="tab"))
    actions = tui.render(RenderConstraints(width=80, max_height=20))
    action_lines = tuple(line.text for line in actions.lines)

    assert "\x1b[1;36m> [Overview]" not in action_lines[2]
    assert "\x1b[1;36m> Open" in action_lines[6]
