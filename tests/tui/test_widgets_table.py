from __future__ import annotations

from typing import Any

from loushang.tui import (
    InputEvent,
    RenderConstraints,
    Table,
    TableColumn,
    TableRow,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Table as UiTable
from loushang.tui.ui_parts import TableColumn as UiTableColumn
from loushang.tui.ui_parts import TableRow as UiTableRow
from loushang.tui.ui_parts.widgets import Table as WidgetTable
from loushang.tui.ui_parts.widgets import TableColumn as WidgetTableColumn
from loushang.tui.ui_parts.widgets import TableRow as WidgetTableRow


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
