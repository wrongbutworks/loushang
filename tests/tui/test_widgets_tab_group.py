from __future__ import annotations

import runpy
from dataclasses import dataclass
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    ThemeResolver,
    strip_control_sequences,
)
from loushang.tui.ui_parts.widgets.tab_group import TabChange, TabGroup, TabPage
from tests.tui.widget_example_playback import play_example


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


@dataclass(slots=True)
class StaticPage:
    lines: tuple[str, ...]

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines(
            [RenderLine(line[: constraints.width]) for line in self.lines[: constraints.max_height]],
            constraints=constraints,
        )


@dataclass(slots=True)
class FocusablePage(StaticPage):
    focused: bool = False
    events: list[str] | None = None

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        key = getattr(event, "key", "")
        if key:
            if self.events is not None:
                self.events.append(key)
            if key == "handled":
                return "page-handled"
            if key == "up":
                return None
        return None


def test_tab_group_normalizes_value_and_renders_selected_page() -> None:
    group = TabGroup(
        [
            TabPage("overview", "Overview", StaticPage(("Overview page",))),
            TabPage("logs", "Logs", StaticPage(("Logs page",))),
        ],
        value="missing",
        content_height=2,
    )

    assert group.selected_value == "overview"
    assert group.selected_page is not None
    assert plain_lines(group, width=40, height=4) == (
        "*[Overview]   [Logs]",
        "Overview page",
        "",
    )


def test_tab_group_fixed_content_height_pads_and_clips() -> None:
    group = TabGroup(
        [TabPage("long", "Long", StaticPage(("one", "two", "three")))],
        content_height=2,
    )

    assert plain_lines(group, width=20, height=5) == (
        "*[Long]",
        "one",
        "two",
    )

    short = TabGroup([TabPage("short", "Short", StaticPage(("one",)))], content_height=3)
    assert plain_lines(short, width=20, height=5) == (
        "*[Short]",
        "one",
        "",
        "",
    )


def test_tab_group_returns_tab_change_without_callback() -> None:
    group = TabGroup(
        [
            TabPage("one", "One", StaticPage(("One",))),
            TabPage("two", "Two", StaticPage(("Two",))),
        ],
        focused=True,
    )

    result = group.handle_input(InputEvent(kind="key", key="right"))

    assert result == TabChange(value="two", previous_value="one", level=0)
    assert group.selected_value == "two"


def test_tab_group_callback_result_takes_precedence() -> None:
    calls: list[str] = []
    group = TabGroup(
        [
            TabPage("one", "One", StaticPage(("One",))),
            TabPage("two", "Two", StaticPage(("Two",))),
        ],
        focused=True,
        on_change=lambda value: calls.append(value),
    )

    assert group.handle_input(InputEvent(kind="key", key="right")) is True
    assert calls == ["two"]


def test_tab_group_down_enters_content_and_up_returns_to_header() -> None:
    page = FocusablePage(("content",), events=[])
    group = TabGroup([TabPage("page", "Page", page)], focused=True)

    assert group.handle_input(InputEvent(kind="key", key="down")) is True
    assert group.header_focused is False
    assert page.focused is True

    assert group.handle_input(InputEvent(kind="key", key="handled")) == "page-handled"
    assert page.events == ["handled"]

    assert group.handle_input(InputEvent(kind="key", key="up")) is True
    assert group.header_focused is True
    assert page.focused is False


def test_tab_group_preserves_page_objects_across_switches() -> None:
    first = FocusablePage(("first",), events=[])
    second = FocusablePage(("second",), events=[])
    group = TabGroup(
        [TabPage("first", "First", first), TabPage("second", "Second", second)],
        focused=True,
    )

    group.focus_content()
    assert first.focused is True
    assert group.handle_input(InputEvent(kind="key", key="right")) == TabChange("second", "first", 0)
    assert first.focused is False
    assert second.focused is True

    group.handle_input(InputEvent(kind="key", key="left"))
    assert first is group.selected_page.content
    assert first.focused is True


def test_tab_group_editor_target_delegates_only_when_content_focused() -> None:
    class EditorPage(FocusablePage):
        def editor_input_target(self) -> object | None:
            return "editor-target" if self.focused else None

    group = TabGroup([TabPage("edit", "Edit", EditorPage(("edit",)))], focused=True)

    assert group.editor_input_target() is None
    assert group.focus_content() is True
    assert group.editor_input_target() == "editor-target"


def test_tab_group_offsets_selected_content_cursor() -> None:
    class CursorPage(StaticPage):
        def render(self, constraints: RenderConstraints) -> RenderResult:
            return RenderResult.from_lines(
                [RenderLine("abc")],
                constraints=constraints,
                cursor=CursorDeclaration(row=0, column=2),
            )

    group = TabGroup([TabPage("edit", "Edit", CursorPage(("abc",)))], focused=True)

    result = group.render(RenderConstraints(width=20, max_height=3))

    assert result.cursor == CursorDeclaration(row=1, column=2)


def test_tab_group_renders_header_only_when_no_content_height_remains() -> None:
    group = TabGroup([TabPage("one", "One", StaticPage(("content",)))])

    assert plain_lines(group, width=20, height=1) == ("*[One]",)


def test_tab_group_uses_distinct_header_and_content_focus_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.tabs.level0.selected_header_focus": {"color": "cyan"},
            "widget.tabs.level0.selected_content_focus": {"color": "green"},
            "widget.tabs.tab": {"color": "white"},
        }
    )
    page = FocusablePage(("content",))
    group = TabGroup([TabPage("main", "Main", page)], focused=True, theme=theme)

    header_raw = render_lines(group, width=40, height=3)[0]
    assert header_raw.startswith("\x1b[36m")

    assert group.focus_content() is True
    content_raw = render_lines(group, width=40, height=3)[0]
    assert content_raw.startswith("\x1b[32m")


def test_nested_tab_group_keeps_parent_selected_content_focus() -> None:
    nested_page = FocusablePage(("nested content",))
    nested = TabGroup([TabPage("overview", "Overview", nested_page)], level=1)
    outer = TabGroup([TabPage("stats", "Stats", nested)], focused=True)

    assert outer.focus_content() is True
    assert nested.focused is True
    assert nested.header_focused is True
    assert outer.header_focused is False

    raw = render_lines(outer, width=60, height=6)
    assert "Stats" in strip_control_sequences(raw[0])
    assert "Overview" in strip_control_sequences(raw[1])


def test_nested_tab_group_markers_follow_active_focus_path() -> None:
    nested_page = FocusablePage(("nested content",))
    nested = TabGroup(
        [
            TabPage("overview", "Overview", nested_page),
            TabPage("models", "Models", StaticPage(("models",))),
        ],
        level=1,
    )
    outer = TabGroup([TabPage("stats", "Stats", nested)], focused=True)

    parent_header = plain_lines(outer, width=80, height=5)
    assert parent_header[0].startswith(">[Stats]")
    assert parent_header[1].startswith("*[Overview]")
    assert sum(line.count(">") for line in parent_header) == 1

    assert outer.focus_content() is True
    child_header = plain_lines(outer, width=80, height=5)
    assert child_header[0].startswith("*[Stats]")
    assert child_header[1].startswith(">[Overview]")
    assert sum(line.count(">") for line in child_header) == 1

    assert outer.handle_input(InputEvent(kind="key", key="down")) is True
    child_content = plain_lines(outer, width=80, height=5)
    assert child_content[0].startswith("*[Stats]")
    assert child_content[1].startswith("*[Overview]")
    assert sum(line.count(">") for line in child_content) == 0

    outer.focus_header()
    parent_header_again = plain_lines(outer, width=80, height=5)
    assert parent_header_again[0].startswith(">[Stats]")
    assert parent_header_again[1].startswith("*[Overview]")
    assert sum(line.count(">") for line in parent_header_again) == 1


def test_nested_tab_group_uses_parent_content_and_child_header_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.tabs.level0.selected_content_focus": {"color": "green"},
            "widget.tabs.level1.selected_header_focus": {"color": "magenta"},
            "widget.tabs.level1.selected_content_focus": {"color": "yellow"},
        }
    )
    nested = TabGroup([TabPage("overview", "Overview", FocusablePage(("nested",)))], level=1, theme=theme)
    outer = TabGroup([TabPage("stats", "Stats", nested)], focused=True, theme=theme)

    assert outer.focus_content() is True
    child_header_raw = render_lines(outer, width=80, height=5)
    assert child_header_raw[0].startswith("\x1b[32m*[Stats]")
    assert child_header_raw[1].startswith("\x1b[35m>[Overview]")

    assert outer.handle_input(InputEvent(kind="key", key="down")) is True
    child_content_raw = render_lines(outer, width=80, height=5)
    assert child_content_raw[0].startswith("\x1b[32m*[Stats]")
    assert child_content_raw[1].startswith("\x1b[33m*[Overview]")


def test_nested_tab_switch_does_not_change_parent_value() -> None:
    nested = TabGroup(
        [
            TabPage("overview", "Overview", StaticPage(("overview",))),
            TabPage("models", "Models", StaticPage(("models",))),
        ],
        level=1,
    )
    outer = TabGroup([TabPage("stats", "Stats", nested)], focused=True)

    outer.focus_content()
    result = outer.handle_input(InputEvent(kind="key", key="right"))

    assert result == TabChange(value="models", previous_value="overview", level=1)
    assert outer.selected_value == "stats"
    assert nested.selected_value == "models"


def test_tabgroup_searchable_list_example_playback_filters_settings() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("type mode", InputEvent(kind="text", text="mode")),
        ),
        width=100,
        height=24,
    )

    initial = frames[0].lines
    filtered = frames[-1].lines

    assert any("Workspace" in line and "Activity" in line for line in initial)
    assert initial[0].startswith(">[Workspace]")
    assert any("Search" in line for line in initial)
    assert any("mode" in line.lower() for line in filtered)
    assert any("Model" in line or "mode" in line for line in filtered)
    assert any("Setting" in line and "Value" in line for line in initial)
    assert any(set(line) == {"-"} for line in initial)


def test_tabgroup_searchable_list_example_styles_top_level_selected_tab() -> None:
    namespace = runpy.run_path("examples/tui/52_widgets_tabgroup_searchable_list.py", run_name="__test__")
    tui = namespace["build_app"]()

    initial = tui.render(RenderConstraints(width=100, max_height=24)).lines[0].text
    assert "\x1b[" in initial
    assert ">[Workspace]" in initial

    for event in (
        InputEvent(kind="key", key="up"),
        InputEvent(kind="key", key="right"),
        InputEvent(kind="key", key="right"),
        InputEvent(kind="key", key="right"),
    ):
        tui.handle_input(event)

    activity = tui.render(RenderConstraints(width=100, max_height=24)).lines[0].text
    assert "\x1b[" in activity
    assert ">[Activity]" in activity


def test_tabgroup_searchable_list_example_playback_switches_nested_tabs() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("up to tabs", InputEvent(kind="key", key="up")),
            ("right models", InputEvent(kind="key", key="right")),
            ("right permissions", InputEvent(kind="key", key="right")),
            ("right activity", InputEvent(kind="key", key="right")),
            ("down nested", InputEvent(kind="key", key="down")),
            ("right nested models", InputEvent(kind="key", key="right")),
        ),
        width=100,
        height=24,
    )

    assert any("Overview" in line and "Models" in line for line in frames[-1].lines)
    assert any("Tokens per Day" in line or "Model usage" in line for line in frames[-1].lines)
    assert any("Overview" in line and ">[Models]" in line for line in frames[-1].lines)


def test_tabgroup_searchable_list_example_up_to_tabs_down_returns_to_search() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("up to tabs", InputEvent(kind="key", key="up")),
            ("down to search", InputEvent(kind="key", key="down")),
        ),
        width=100,
        height=24,
    )

    assert frames[-1].lines[0].startswith(">[Workspace]")
    assert frames[-1].lines[2] == "Search settings..."
    assert not any(line.startswith("> Model") for line in frames[-1].lines)
    assert frames[-1].lines[-1].startswith("Search |")


def test_tabgroup_searchable_list_example_playback_scrolls_long_list_without_layout_jump() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=tuple((f"down {index}", InputEvent(kind="key", key="down")) for index in range(18)),
        width=100,
        height=24,
    )

    footer_rows = [
        next(index for index, line in enumerate(frame.lines) if "Enter" in line or "filter" in line)
        for frame in frames
    ]
    assert len(set(footer_rows)) == 1
    assert any("more below" in line.lower() or "more above" in line.lower() for line in frames[-1].lines)


def test_tabgroup_searchable_list_example_playback_page_keys_and_edges() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("down to list", InputEvent(kind="key", key="down")),
            ("page down", InputEvent(kind="key", key="pageDown")),
            ("end", InputEvent(kind="key", key="end")),
            ("page up", InputEvent(kind="key", key="pageUp")),
            ("home", InputEvent(kind="key", key="home")),
        ),
        width=100,
        height=24,
    )

    assert any("more below" in line.lower() for line in frames[0].lines)
    assert any("more above" in line.lower() or "more below" in line.lower() for line in frames[2].lines)
    assert any("more below" in line.lower() for line in frames[-1].lines)


def test_tabgroup_searchable_list_example_playback_preserves_list_state_across_tabs() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("down to list", InputEvent(kind="key", key="down")),
            ("page down", InputEvent(kind="key", key="pageDown")),
            ("page down again", InputEvent(kind="key", key="pageDown")),
            ("shift tab to top tabs", InputEvent(kind="key", key="shift+tab")),
            ("right models", InputEvent(kind="key", key="right")),
            ("left workspace", InputEvent(kind="key", key="left")),
            ("down content", InputEvent(kind="key", key="down")),
        ),
        width=100,
        height=24,
    )

    final = "\n".join(frames[-1].lines).lower()
    assert "more above" in final


def test_tabgroup_searchable_list_example_playback_selects_and_toggles_settings() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("enter select", InputEvent(kind="key", key="enter")),
            ("type compact", InputEvent(kind="text", text="compact")),
            ("space toggle", InputEvent(kind="key", key="space")),
        ),
        width=100,
        height=24,
    )

    assert any("Selected: Model" in line for line in frames[1].lines)
    assert any("Auto-compact" in line and "true" in line for line in frames[-1].lines)
    assert any("Toggled: Auto-compact" in line for line in frames[-1].lines)


def test_tabgroup_searchable_list_example_printable_space_toggles_setting() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("type compact", InputEvent(kind="text", text="compact")),
            ("space toggle", InputEvent(kind="text", text=" ")),
        ),
        width=100,
        height=24,
    )

    assert any(line.startswith("> Auto-compact") and "true" in line for line in frames[-1].lines)
    assert any("Toggled: Auto-compact" in line for line in frames[-1].lines)
    assert frames[-1].lines[-1].startswith("Settings |")


def test_tabgroup_searchable_list_example_quit_keys_are_global() -> None:
    namespace = runpy.run_path("examples/tui/52_widgets_tabgroup_searchable_list.py", run_name="__test__")
    should_quit = namespace["_should_quit"]

    assert should_quit(InputEvent(kind="text", text="q"))
    assert should_quit(InputEvent(kind="key", key="q"))
    assert should_quit(InputEvent(kind="key", key="ctrl+c"))
