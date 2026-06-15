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
