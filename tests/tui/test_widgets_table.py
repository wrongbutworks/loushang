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
