from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from loushang.tui import (
    CompactNumberFormatter,
    DataGrid,
    DataGridCell,
    DataGridColumn,
    DataGridFormatResult,
    DataGridRow,
    DeltaFormatter,
    InputEvent,
    NumberFormatter,
    PercentFormatter,
    RenderConstraints,
    TextFormatter,
    strip_control_sequences,
)
from loushang.tui.ui_parts import DataGrid as UiDataGrid
from loushang.tui.ui_parts.widgets import DataGrid as WidgetDataGrid


def plain_lines(part: Any, *, width: int = 80, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)


def test_data_grid_is_reexported_from_public_modules() -> None:
    assert DataGrid is UiDataGrid
    assert DataGrid is WidgetDataGrid
    assert DataGridColumn("code", "Code").key == "code"
    assert DataGridCell("AAPL").value == "AAPL"
    assert DataGridRow("row-1", {"code": "AAPL"}).key == "row-1"


def test_data_grid_formatters_cover_text_number_percent_delta_and_compact_values() -> None:
    assert TextFormatter()(None) == ""
    assert TextFormatter(none_text="N/A")(None) == "N/A"
    assert NumberFormatter(precision=2)(Decimal("1234.5")) == "1234.50"
    assert NumberFormatter(precision=2, thousands=True, sign=True)(1234.5) == "+1,234.50"
    assert NumberFormatter(precision=None)(Decimal("12.3400")) == "12.34"
    assert PercentFormatter(precision=2, sign=True)(0.0345) == "+3.45%"
    assert DeltaFormatter(precision=2)(-1.2) == "-1.20"
    assert CompactNumberFormatter(precision=1)(1250000) == "1.3M"
    assert NumberFormatter(precision=2, invalid_text="bad")(float("nan")) == "bad"
    assert PercentFormatter(none_text="empty")(None) == "empty"


def test_data_grid_normalizes_mapping_list_tuple_rows_and_cell_metadata() -> None:
    grid = DataGrid(
        [
            DataGridColumn("code", "Code"),
            DataGridColumn("qty", "Qty", formatter=NumberFormatter(precision=0), align="right"),
            DataGridColumn("hidden", "Hidden", hidden=True),
        ],
        [
            {"code": "AAPL", "qty": 5},
            ["MSFT", DataGridCell(3, disabled=True), "secret"],
            DataGridRow("explicit", {"code": "NVDA", "qty": None}, label="Nvidia"),
        ],
    )

    assert grid.row_keys == ("row-0", "row-1", "explicit")
    assert grid.active_row_key == "row-0"
    assert grid.active_column_key == "code"
    assert grid.cell_value("row-1", "hidden") == "secret"
    assert grid.cell_disabled("row-1", "qty") is True
    lines = plain_lines(grid, width=32, height=5)

    assert lines[0].startswith("  Code")
    assert lines[0].endswith("Qty")
    assert lines[1].startswith("  AAPL")
    assert lines[1].endswith("5")
    assert lines[2].startswith("  MSFT")
    assert lines[2].endswith("3")
    assert lines[3].startswith("  NVDA")
    assert "Hidden" not in "\n".join(lines)


def test_data_grid_applies_custom_formatter_results_to_rendered_text() -> None:
    def status_formatter(value: object) -> DataGridFormatResult:
        return DataGridFormatResult(text=f"[{value}]", theme_token="example.status")

    grid = DataGrid(
        [DataGridColumn("job", "Job"), DataGridColumn("status", "Status", formatter=status_formatter)],
        [{"job": "Build", "status": "ready"}],
    )

    lines = plain_lines(grid, width=32, height=3)

    assert lines[0].startswith("  Job")
    assert lines[0].endswith("Status")
    assert lines[1].startswith("  Build")
    assert lines[1].endswith("[ready]")


def test_data_grid_rejects_duplicate_keys_and_string_rows() -> None:
    with pytest.raises(ValueError, match="duplicate column"):
        DataGrid([DataGridColumn("code", "Code"), DataGridColumn("code", "Other")], [])

    with pytest.raises(ValueError, match="duplicate row"):
        DataGrid(
            [DataGridColumn("code", "Code")],
            [
                DataGridRow("same", {"code": "A"}),
                DataGridRow("same", {"code": "B"}),
            ],
        )

    with pytest.raises(TypeError, match="mapping, list, tuple, or DataGridRow"):
        DataGrid([DataGridColumn("code", "Code")], ["AAPL"])  # type: ignore[list-item]


def test_data_grid_row_mode_navigation_skips_disabled_and_pinned_rows() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [
            DataGridRow("summary", {"job": "Summary"}, pinned="top"),
            DataGridRow("build", {"job": "Build"}),
            DataGridRow("archive", {"job": "Archive"}, disabled=True),
            DataGridRow("deploy", {"job": "Deploy"}),
            DataGridRow("total", {"job": "Total"}, pinned="bottom"),
        ],
        wrap_rows=False,
    )

    assert grid.active_row_key == "build"
    assert grid.handle_input(InputEvent(kind="key", key="down")) is True
    assert grid.active_row_key == "deploy"
    assert grid.handle_input(InputEvent(kind="key", key="down")) is False
    assert grid.active_row_key == "deploy"
    assert grid.handle_input(InputEvent(kind="key", key="up")) is True
    assert grid.active_row_key == "build"
    assert grid.handle_input(InputEvent(kind="key", key="left")) is False
    assert grid.handle_input(InputEvent(kind="key", key="end")) is True
    assert grid.active_row_key == "deploy"
    assert grid.handle_input(InputEvent(kind="key", key="home")) is True
    assert grid.active_row_key == "build"


def test_data_grid_row_navigation_wraps_when_enabled() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [
            DataGridRow("build", {"job": "Build"}),
            DataGridRow("deploy", {"job": "Deploy"}),
        ],
    )

    assert grid.active_row_key == "build"
    assert grid.handle_input(InputEvent(kind="key", key="up")) is True
    assert grid.active_row_key == "deploy"
    assert grid.handle_input(InputEvent(kind="key", key="down")) is True
    assert grid.active_row_key == "build"


def test_data_grid_cell_mode_repairs_and_navigates_enabled_cells() -> None:
    grid = DataGrid(
        [
            DataGridColumn("code", "Code"),
            DataGridColumn("qty", "Qty"),
            DataGridColumn("hidden", "Hidden", hidden=True),
            DataGridColumn("note", "Note"),
        ],
        [
            DataGridRow("a", {"code": "AAPL", "qty": DataGridCell(5, disabled=True), "note": "buy"}),
            DataGridRow("b", {"code": DataGridCell("MSFT", disabled=True), "qty": 2, "note": "hold"}),
        ],
        active_row_key="a",
        active_column_key="qty",
        cursor_mode="cell",
        wrap_columns=False,
    )

    assert (grid.active_row_key, grid.active_column_key) == ("a", "code")
    assert grid.handle_input(InputEvent(kind="key", key="right")) is True
    assert (grid.active_row_key, grid.active_column_key) == ("a", "note")
    assert grid.handle_input(InputEvent(kind="key", key="right")) is False
    assert (grid.active_row_key, grid.active_column_key) == ("a", "note")
    assert grid.handle_input(InputEvent(kind="key", key="down")) is True
    assert (grid.active_row_key, grid.active_column_key) == ("b", "note")
    assert grid.handle_input(InputEvent(kind="key", key="home")) is True
    assert (grid.active_row_key, grid.active_column_key) == ("b", "qty")


def test_data_grid_column_mode_moves_only_visible_columns() -> None:
    grid = DataGrid(
        [
            DataGridColumn("code", "Code"),
            DataGridColumn("hidden", "Hidden", hidden=True),
            DataGridColumn("qty", "Qty"),
        ],
        [{"code": "AAPL", "hidden": "secret", "qty": 5}],
        active_column_key="hidden",
        cursor_mode="column",
        wrap_columns=False,
    )

    assert grid.active_row_key == "row-0"
    assert grid.active_column_key == "code"
    assert grid.handle_input(InputEvent(kind="key", key="down")) is False
    assert grid.active_row_key == "row-0"
    assert grid.handle_input(InputEvent(kind="key", key="right")) is True
    assert grid.active_column_key == "qty"
    assert grid.handle_input(InputEvent(kind="key", key="right")) is False
    assert grid.active_column_key == "qty"
    assert grid.handle_input(InputEvent(kind="key", key="home")) is True
    assert grid.active_column_key == "code"


def test_data_grid_none_mode_repairs_public_state_but_consumes_no_navigation() -> None:
    grid = DataGrid(
        [
            DataGridColumn("hidden", "Hidden", hidden=True),
            DataGridColumn("code", "Code"),
        ],
        [
            DataGridRow("skip", {"code": "Skip"}, disabled=True),
            DataGridRow("build", {"code": "Build"}),
        ],
        active_row_key="skip",
        active_column_key="hidden",
        cursor_mode="none",
    )

    assert (grid.active_row_key, grid.active_column_key) == ("build", "code")
    assert grid.handle_input(InputEvent(kind="key", key="down")) is None
    assert (grid.active_row_key, grid.active_column_key) == ("build", "code")
