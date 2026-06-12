from __future__ import annotations

import runpy
from typing import Any

from loushang.tui import (
    InputEvent,
    RenderConstraints,
    Table,
    TableColumn,
    TableRow,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Table as UiTable
from loushang.tui.ui_parts import TableColumn as UiTableColumn
from loushang.tui.ui_parts import TableRow as UiTableRow
from loushang.tui.ui_parts.widgets import Table as WidgetTable
from loushang.tui.ui_parts.widgets import TableColumn as WidgetTableColumn
from loushang.tui.ui_parts.widgets import TableRow as WidgetTableRow
from tests.tui.widget_example_playback import play_example


def render_lines(part: Any, *, width: int = 60, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 60, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def test_table_widgets_are_reexported_from_public_modules() -> None:
    assert Table is UiTable
    assert Table is WidgetTable
    assert TableColumn is UiTableColumn
    assert TableColumn is WidgetTableColumn
    assert TableRow is UiTableRow
    assert TableRow is WidgetTableRow
    assert TableColumn("name", "Name").key == "name"
    assert TableRow("row-1", {"name": "Tower"}).value == "row-1"


def test_table_normalizes_mapping_sequence_rows_and_column_config() -> None:
    table = Table(
        [
            TableColumn("name", "Name", width=-5, min_width=-1),
            TableColumn("status", "Status"),
        ],
        [
            {"name": "", "status": "ready"},
            {"name": None, "status": "idle"},
            ("coded", "done"),
        ],
    )

    assert table.handle_input(InputEvent(kind="key", key="enter")) == "ready"
    assert table.handle_input(InputEvent(kind="key", key="down")) is True
    assert table.handle_input(InputEvent(kind="key", key="enter")) == "idle"
    assert table.handle_input(InputEvent(kind="key", key="down")) is True
    assert table.handle_input(InputEvent(kind="key", key="enter")) == "coded"
    assert_widths_within(render_lines(table, width=12, height=4), 12)


def test_table_renders_header_rows_fixed_flexible_widths_and_alignment() -> None:
    table = Table(
        [
            TableColumn("name", "Name", width=8),
            TableColumn("status", "Status"),
            TableColumn("count", "Count", width=5, align="right"),
        ],
        [
            TableRow("build", {"name": "Build", "status": "ready", "count": 12}),
            TableRow("deploy", {"name": "Deploy", "status": "blocked", "count": 3}),
        ],
    )

    assert plain_lines(table, width=34, height=4) == (
        "  Name      Status          Count",
        "  Build     ready              12",
        "  Deploy    blocked             3",
    )


def test_table_truncates_narrow_width_and_short_height() -> None:
    table = Table(
        [
            TableColumn("name", "Name", width=8),
            TableColumn("status", "Status"),
        ],
        [
            TableRow("one", {"name": "LongName", "status": "VeryLongStatus"}),
            TableRow("two", {"name": "Second", "status": "Done"}),
        ],
    )

    assert plain_lines(table, width=16, height=2) == (
        "  Name      Sta",
        "  LongName  Ver",
    )
    assert_widths_within(render_lines(table, width=1, height=3), 1)


def test_table_column_widths_honor_min_width_then_shrink_right_to_left() -> None:
    table = Table(
        [
            TableColumn("id", "ID", width=1, min_width=3),
            TableColumn("name", "Name", min_width=4),
            TableColumn("note", "Note", width=20),
        ],
        [
            {"id": "ABCDE", "name": "WXYZ", "note": "tail"},
        ],
    )

    assert plain_lines(table, width=15, height=2) == (
        "  ID   Name  N",
        "  ABC  WXYZ  t",
    )


def test_table_empty_and_no_column_rendering() -> None:
    with_columns = Table([TableColumn("name", "Name")], [])
    no_columns = Table([], [])

    assert plain_lines(with_columns, width=12, height=3) == (
        "  Name",
        "  No rows",
    )
    assert plain_lines(no_columns, width=12, height=3) == ("No rows",)


def test_table_can_hide_header() -> None:
    table = Table(
        [TableColumn("name", "Name")],
        [TableRow("one", {"name": "One"})],
        show_header=False,
    )

    assert plain_lines(table, width=12, height=2) == ("  One",)


def test_table_navigation_activation_callbacks_and_space_forms() -> None:
    calls: list[str] = []
    table = Table(
        [TableColumn("name", "Name")],
        [
            TableRow("build", {"name": "Build"}, on_select=lambda: calls.append("build")),
            TableRow("disabled", {"name": "Disabled"}, disabled=True),
            TableRow("deploy", {"name": "Deploy"}, on_select=lambda: "deploy"),
        ],
    )
    table.focus()

    assert table.active_value == "build"
    assert plain_lines(table, width=20, height=4)[1] == "> Build"
    assert table.handle_input(InputEvent(kind="key", key="enter")) is True
    assert table.handle_input(InputEvent(kind="key", key="down")) is True
    assert table.active_value == "deploy"
    assert table.handle_input(InputEvent(kind="key", key="enter")) == "deploy"
    assert table.handle_input(InputEvent(kind="key", key="down")) is True
    assert table.active_value == "build"
    assert table.handle_input(InputEvent(kind="text", text=" ")) is True
    assert table.handle_input(InputEvent(kind="key", key="space")) is True
    assert calls == ["build", "build", "build"]


def test_table_wrap_false_boundaries_empty_disabled_and_height_window() -> None:
    table = Table(
        [TableColumn("name", "Name")],
        [
            TableRow("one", {"name": "One"}),
            TableRow("two", {"name": "Two"}),
            TableRow("three", {"name": "Three"}),
        ],
        wrap=False,
    )
    table.focus()

    assert table.handle_input(InputEvent(kind="key", key="up")) is False
    assert table.handle_input(InputEvent(kind="key", key="end")) is True
    assert table.active_value == "three"
    assert table.handle_input(InputEvent(kind="key", key="down")) is False
    assert table.handle_input(InputEvent(kind="key", key="home")) is True
    assert table.active_value == "one"

    assert Table([], []).handle_input(InputEvent(kind="key", key="down")) is None
    disabled = Table([TableColumn("name", "Name")], [TableRow("no", {"name": "No"}, disabled=True)])
    disabled.focus()
    assert disabled.handle_input(InputEvent(kind="key", key="down")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None

    windowed = Table(
        [TableColumn("name", "Name")],
        [TableRow(str(index), {"name": f"Item {index}"}) for index in range(5)],
        active_index=4,
    )
    windowed.focus()
    assert plain_lines(windowed, width=20, height=3) == (
        "  Name",
        "  Item 3",
        "> Item 4",
    )


def test_table_applies_theme_tokens_and_preserves_visible_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.table.header": {"color": "cyan"},
            "widget.table.row": {"color": "white"},
            "widget.table.focus": {"bold": True, "color": "green"},
            "widget.table.disabled": {"dim": True},
            "widget.table.empty": {"color": "bright_black"},
        }
    )
    table = Table(
        [TableColumn("name", "Name")],
        [
            TableRow("build", {"name": "Build"}),
            TableRow("skip", {"name": "Skip"}, disabled=True),
        ],
        theme=theme,
    )
    table.focus()

    raw = render_lines(table, width=20, height=3)

    assert raw[0].startswith("\x1b[36m  Name")
    assert raw[1].startswith("\x1b[1;32m> Build")
    assert raw[2].startswith("\x1b[2m  Skip")
    assert plain_lines(table, width=20, height=3) == (
        "  Name",
        "> Build",
        "  Skip",
    )
    assert_widths_within(raw, 20)


def test_table_empty_state_uses_theme_and_width_rules() -> None:
    theme = ThemeResolver(defaults={"widget.table.empty": {"color": "bright_black"}})

    no_columns = Table([], [], empty_text="Nothing here", theme=theme)
    with_columns = Table([TableColumn("name", "Name")], [], empty_text="Nothing here", theme=theme)

    assert render_lines(no_columns, width=8, height=2)[0].startswith("\x1b[90mNothing")
    assert plain_lines(no_columns, width=8, height=2) == ("Nothing",)
    assert plain_lines(with_columns, width=12, height=3) == (
        "  Name",
        "  Nothing h",
    )


def test_widgets_table_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/46_widgets_table.py", run_name="__test__")

    build_app = namespace["build_app"]
    assert callable(build_app)
    app = build_app()
    result = app.render(RenderConstraints(width=80, max_height=20))
    assert result.lines


def test_widgets_table_example_playback_snapshots() -> None:
    frames = play_example(
        "examples/tui/46_widgets_table.py",
        events=(
            ("down", InputEvent(kind="key", key="down")),
            ("enter", InputEvent(kind="key", key="enter")),
        ),
    )

    assert frames[0].lines[:8] == (
        "Job Queue  (3 jobs)",
        "",
        "  Job           Status                                                     Runs",
        "> Build         ready                                                        12",
        "  Deploy        blocked                                                       3",
        "  Archive       disabled                                                      0",
        "",
        "Selected      Build is ready, 12 runs",
    )
    assert "> Deploy        blocked" in "\n".join(frames[1].lines)
    assert "Selected      Deploy is blocked, 3 runs" in frames[2].lines
