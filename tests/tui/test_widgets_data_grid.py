from __future__ import annotations

import runpy
from decimal import Decimal
from typing import Any

import pytest

from loushang.tui import (
    CompactNumberFormatter,
    CursorDeclaration,
    DataGrid,
    DataGridCell,
    DataGridColumn,
    DataGridEdit,
    DataGridFormatResult,
    DataGridFilterMode,
    DataGridRow,
    DataGridRowView,
    DataGridSelect,
    DataGridSelectionChange,
    DeltaFormatter,
    InputEvent,
    NumberFormatter,
    PercentFormatter,
    RenderConstraints,
    TextFormatter,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import DataGrid as UiDataGrid
from loushang.tui.ui_parts.widgets import DataGrid as WidgetDataGrid
from tests.tui.widget_example_playback import play_example


def plain_lines(part: Any, *, width: int = 80, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)


def render_lines(part: Any, *, width: int = 80, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def test_data_grid_is_reexported_from_public_modules() -> None:
    assert DataGrid is UiDataGrid
    assert DataGrid is WidgetDataGrid
    assert DataGridColumn("code", "Code").key == "code"
    assert DataGridCell("AAPL").value == "AAPL"
    assert DataGridRow("row-1", {"code": "AAPL"}).key == "row-1"
    assert DataGridRowView("row-1", {"code": "AAPL"}).key == "row-1"
    mode: DataGridFilterMode = "contains"
    assert mode == "contains"


def test_data_grid_filter_state_defaults_and_column_searchable_flag() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code"), DataGridColumn("secret", "Secret", searchable=False)],
        [DataGridRow("a", {"code": "AAPL", "secret": "hidden"})],
    )

    assert grid.filter_query == ""
    assert grid.filter_query_columns is None
    assert grid.filter_mode == "contains"
    assert grid.filter_case_sensitive is False
    assert grid.has_filter is False
    assert grid.view_row_keys == ("a",)
    assert grid.filtered_row_count == 1
    assert grid.total_body_row_count == 1
    assert grid.columns[1].searchable is False


def test_data_grid_filter_query_matches_visible_searchable_raw_values() -> None:
    grid = DataGrid(
        [
            DataGridColumn("symbol", "Symbol"),
            DataGridColumn("sector", "Sector"),
            DataGridColumn("hidden", "Hidden", hidden=True),
            DataGridColumn("secret", "Secret", searchable=False),
        ],
        [
            DataGridRow("a", {"symbol": "AAPL", "sector": "AI", "hidden": "ghost", "secret": "private"}),
            DataGridRow("m", {"symbol": "MSFT", "sector": "Cloud", "hidden": "x", "secret": "AAPL"}),
            DataGridRow("n", {"symbol": "NVDA", "sector": None, "hidden": "aapl", "secret": "x"}),
        ],
    )

    assert grid.set_filter_query("aap") is True
    assert grid.view_row_keys == ("a",)
    assert grid.row_keys == ("a", "m", "n")

    assert grid.set_filter_query("A", columns=("sector",), mode="prefix") is True
    assert grid.filter_query_columns == ("sector",)
    assert grid.view_row_keys == ("a",)

    assert grid.set_filter_query("a", columns=("hidden", "secret", "missing")) is True
    assert grid.filter_query_columns == ()
    assert grid.view_row_keys == ()


def test_data_grid_filter_query_case_sensitive_and_none_normalization() -> None:
    grid = DataGrid(
        [DataGridColumn("value", "Value")],
        [DataGridRow("upper", {"value": "AAPL"}), DataGridRow("none", {"value": None})],
    )

    assert grid.set_filter_query("aapl", case_sensitive=True) is True
    assert grid.view_row_keys == ()

    assert grid.set_filter_query("   ", case_sensitive=True, mode="prefix", columns=("value",)) is True
    assert grid.filter_query == ""
    assert grid.filter_query_columns is None
    assert grid.filter_mode == "contains"
    assert grid.filter_case_sensitive is False

    assert grid.set_filter_query("none") is True
    assert grid.view_row_keys == ()


def test_data_grid_filter_predicate_combines_with_query_and_uses_row_view() -> None:
    seen: list[tuple[str, dict[str, object], bool]] = []
    grid = DataGrid(
        [
            DataGridColumn("symbol", "Symbol"),
            DataGridColumn("price", "Price"),
            DataGridColumn("hidden", "Hidden", hidden=True),
        ],
        [
            DataGridRow("a", {"symbol": "AAPL", "price": 210, "hidden": "visible-to-predicate"}),
            DataGridRow("m", {"symbol": "MSFT", "price": 420, "hidden": "x"}, disabled=True),
            DataGridRow("n", {"symbol": "NVDA", "price": 120, "hidden": "x"}),
        ],
    )

    def predicate(row: DataGridRowView) -> bool:
        seen.append((row.key, dict(row.values), row.disabled))
        return float(row.values["price"]) >= 200

    assert grid.set_filter_query("t") is True
    assert grid.set_filter_predicate(predicate) is True

    assert grid.view_row_keys == ("m",)
    assert ("m", {"symbol": "MSFT", "price": 420, "hidden": "x"}, True) in seen


def test_data_grid_filter_predicate_exceptions_propagate() -> None:
    grid = DataGrid([DataGridColumn("name", "Name")], [DataGridRow("a", {"name": "A"})])

    with pytest.raises(RuntimeError, match="bad predicate"):
        grid.set_filter_predicate(lambda row: (_ for _ in ()).throw(RuntimeError("bad predicate")))


def test_data_grid_filter_render_navigation_and_empty_body_view() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [
            DataGridRow("top", {"job": "Pinned top"}, pinned="top"),
            DataGridRow("build", {"job": "Build"}),
            DataGridRow("deploy", {"job": "Deploy"}),
            DataGridRow("bottom", {"job": "Pinned bottom"}, pinned="bottom"),
        ],
        active_row_key="deploy",
        empty_text="No matches",
        wrap_rows=False,
    )

    assert grid.set_filter_query("build") is True
    assert grid.active_row_key == "build"
    assert grid.view_row_keys == ("build",)
    assert grid.handle_input(InputEvent(kind="key", key="down")) is False

    lines = plain_lines(grid, width=32, height=6)
    assert any("Pinned top" in line for line in lines)
    assert any("Build" in line for line in lines)
    assert any("Pinned bottom" in line for line in lines)
    assert not any("Deploy" in line for line in lines)

    assert grid.set_filter_query("missing") is True
    assert grid.active_row_key is None
    lines = plain_lines(grid, width=32, height=6)
    assert any("Pinned top" in line for line in lines)
    assert any("No matches" in line for line in lines)


def test_data_grid_filtered_large_viewport_formats_only_visible_rows() -> None:
    formatted: list[int] = []

    def counted_formatter(value: object) -> str:
        formatted.append(int(value))
        return f"Item {value}"

    grid = DataGrid(
        [DataGridColumn("name", "Name", formatter=counted_formatter)],
        [DataGridRow(str(index), {"name": index}) for index in range(10_000)],
        active_row_key="9999",
    )

    assert grid.set_filter_predicate(lambda row: int(row.values["name"]) >= 9_997) is True
    lines = plain_lines(grid, width=24, height=4)

    assert any("Item 9999" in line for line in lines)
    assert formatted == [9997, 9998, 9999]


def test_data_grid_filter_blocks_activation_for_filtered_disabled_and_pinned_rows() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job"), DataGridColumn("runs", "Runs")],
        [
            DataGridRow("top", {"job": "Top", "runs": 0}, pinned="top"),
            DataGridRow("build", {"job": "Build", "runs": 12}),
            DataGridRow("skip", {"job": "Skip", "runs": 0}, disabled=True),
            DataGridRow("deploy", {"job": "Deploy", "runs": 3}),
        ],
        cursor_mode="cell",
    )

    assert grid.set_filter_query("build") is True
    assert grid.activate_row("deploy") is False
    assert grid.activate_cell("deploy", "job") is False
    assert grid.activate_row("skip") is False
    assert grid.activate_row("top") is False
    assert grid.activate_row("build") is False


def test_data_grid_filter_scopes_selection_and_preserves_hidden_selection_keys() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [DataGridRow("build", {"job": "Build"}), DataGridRow("deploy", {"job": "Deploy"})],
        selection_mode="multi",
    )

    assert grid.select_row("deploy") is True
    assert grid.set_filter_query("build") is True
    assert grid.selected_row_keys == frozenset({"deploy"})
    assert grid.select_all() is True
    assert grid.selected_row_keys == frozenset({"build"})


def test_data_grid_filter_cancels_edit_when_editing_row_is_filtered_out() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code", editable=True)],
        [DataGridRow("a", {"code": "AAPL"}), DataGridRow("m", {"code": "MSFT"})],
        cursor_mode="cell",
    )

    assert grid.start_edit("m", "code") is True
    assert grid.set_filter_query("AAPL") is True
    assert grid.editing_cell_key is None


def test_data_grid_filter_query_columns_repair_when_columns_hidden_or_removed() -> None:
    grid = DataGrid(
        [DataGridColumn("symbol", "Symbol"), DataGridColumn("sector", "Sector")],
        [DataGridRow("a", {"symbol": "AAPL", "sector": "AI"})],
    )

    assert grid.set_filter_query("AI", columns=("sector",)) is True
    assert grid.view_row_keys == ("a",)
    assert grid.set_column_hidden("sector") is True
    assert grid.filter_query_columns == ()
    assert grid.view_row_keys == ()

    assert grid.set_filter_query("AAPL", columns=("symbol",)) is True
    assert grid.remove_column("symbol") is True
    assert grid.filter_query_columns == ()
    assert grid.view_row_keys == ()


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


def test_data_grid_from_records_infers_columns_and_preserves_first_seen_order() -> None:
    grid = DataGrid.from_records(
        [
            {"symbol": "AAPL", "price": 196.45},
            {"price": 421.10, "symbol": "MSFT", "change_pct": 0.014},
        ],
        cursor_mode="cell",
    )

    assert tuple(column.key for column in grid.columns) == ("symbol", "price", "change_pct")
    assert tuple(column.header for column in grid.columns) == ("Symbol", "Price", "Change Pct")
    assert grid.row_keys == ("row-0", "row-1")
    assert grid.active_row_key == "row-0"
    assert grid.active_column_key == "symbol"
    assert grid.cell_value("row-0", "change_pct") == ""
    assert grid.cell_value("row-1", "change_pct") == 0.014


def test_data_grid_from_records_uses_explicit_columns_and_row_key_field() -> None:
    grid = DataGrid.from_records(
        [
            {"id": "aapl", "symbol": "AAPL", "price": 196.45, "ignored": True},
            {"id": "msft", "symbol": "MSFT", "price": 421.10, "ignored": True},
        ],
        columns=[
            DataGridColumn("symbol", "Ticker"),
            DataGridColumn("price", "Last", align="right", formatter=NumberFormatter(precision=2)),
        ],
        row_key_field="id",
    )

    assert tuple(column.header for column in grid.columns) == ("Ticker", "Last")
    assert grid.row_keys == ("aapl", "msft")
    assert grid.cell_value("aapl", "symbol") == "AAPL"
    assert grid.cell_value("aapl", "price") == 196.45
    assert grid.cell_value("aapl", "ignored") is None


def test_data_grid_from_json_accepts_top_level_records_and_record_wrappers() -> None:
    top_level = DataGrid.from_json('[{"job": "Build", "runs": 12}]')
    wrapped = DataGrid.from_json({"records": [{"job": "Deploy", "runs": 3}]})

    assert tuple(column.key for column in top_level.columns) == ("job", "runs")
    assert top_level.cell_value("row-0", "job") == "Build"
    assert wrapped.cell_value("row-0", "job") == "Deploy"
    assert wrapped.cell_value("row-0", "runs") == 3


def test_data_grid_from_csv_reads_headers_and_rows() -> None:
    grid = DataGrid.from_csv(
        "symbol,price,change_pct\nAAPL,196.45,0.014\nMSFT,421.10,-0.003\n",
        row_key_field="symbol",
    )

    assert tuple(column.key for column in grid.columns) == ("symbol", "price", "change_pct")
    assert grid.row_keys == ("AAPL", "MSFT")
    assert grid.cell_value("AAPL", "price") == "196.45"
    assert grid.cell_value("MSFT", "change_pct") == "-0.003"


def test_data_grid_from_csv_accepts_csv_options_and_grid_options() -> None:
    grid = DataGrid.from_csv(
        "symbol;price\nAAPL;196.45\n",
        csv_options={"delimiter": ";"},
        cursor_mode="cell",
        show_header=False,
    )

    assert tuple(column.key for column in grid.columns) == ("symbol", "price")
    assert grid.cell_value("row-0", "price") == "196.45"
    assert grid.cursor_mode == "cell"
    assert grid.show_header is False


def test_data_grid_adapters_reject_unsupported_shapes() -> None:
    with pytest.raises(TypeError, match="records must contain mappings"):
        DataGrid.from_records([{"job": "Build"}, ["Deploy"]])  # type: ignore[list-item]

    with pytest.raises(ValueError, match="row_key_field"):
        DataGrid.from_records([{"job": "Build"}], row_key_field="id")

    with pytest.raises(ValueError, match="JSON"):
        DataGrid.from_json("{")

    with pytest.raises(ValueError, match="records"):
        DataGrid.from_json({"items": [{"job": "Build"}]})

    with pytest.raises(ValueError, match="header"):
        DataGrid.from_csv("")


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


def test_data_grid_row_mode_ctrl_f_and_ctrl_b_page_rows() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [DataGridRow(f"row-{index}", {"job": f"Job {index}"}) for index in range(12)],
        wrap_rows=False,
    )

    assert grid.active_row_key == "row-0"
    assert grid.handle_input(InputEvent(kind="key", key="ctrl-f")) is True
    assert grid.active_row_key == "row-5"
    assert grid.handle_input(InputEvent(kind="key", key="ctrl-b")) is True
    assert grid.active_row_key == "row-0"


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


def test_data_grid_cell_mode_ctrl_f_and_ctrl_b_page_rows() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code"), DataGridColumn("qty", "Qty")],
        [DataGridRow(f"row-{index}", {"code": f"C{index}", "qty": index}) for index in range(12)],
        active_column_key="qty",
        cursor_mode="cell",
        wrap_rows=False,
    )

    assert (grid.active_row_key, grid.active_column_key) == ("row-0", "qty")
    assert grid.handle_input(InputEvent(kind="key", key="ctrl_f")) is True
    assert (grid.active_row_key, grid.active_column_key) == ("row-5", "qty")
    assert grid.handle_input(InputEvent(kind="key", key="ctrl_b")) is True
    assert (grid.active_row_key, grid.active_column_key) == ("row-0", "qty")


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


def test_data_grid_row_rendering_scrolls_active_row_and_declares_cursor() -> None:
    grid = DataGrid(
        [DataGridColumn("name", "Name", width=8)],
        [DataGridRow(str(index), {"name": f"Item {index}"}) for index in range(6)],
        active_row_key="5",
        focused=True,
        wrap_rows=False,
    )

    result = grid.render(RenderConstraints(width=16, max_height=3))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert lines == (
        "  Name",
        "  Item 4",
        "> Item 5",
    )
    assert result.cursor == CursorDeclaration(row=2, column=0)


def test_data_grid_cell_and_column_modes_declare_cursor_without_confusing_row_prefixes() -> None:
    cell_grid = DataGrid(
        [DataGridColumn("code", "Code", width=5), DataGridColumn("qty", "Qty", width=3, align="right")],
        [DataGridRow("a", {"code": "AAPL", "qty": 5})],
        active_row_key="a",
        active_column_key="qty",
        cursor_mode="cell",
        focused=True,
    )
    column_grid = DataGrid(
        [DataGridColumn("code", "Code", width=5), DataGridColumn("qty", "Qty", width=3, align="right")],
        [DataGridRow("a", {"code": "AAPL", "qty": 5})],
        active_column_key="qty",
        cursor_mode="column",
        focused=True,
    )

    cell_result = cell_grid.render(RenderConstraints(width=16, max_height=3))
    column_result = column_grid.render(RenderConstraints(width=16, max_height=3))
    cell_lines = tuple(strip_control_sequences(line.text).rstrip() for line in cell_result.lines)
    column_lines = tuple(strip_control_sequences(line.text).rstrip() for line in column_result.lines)

    assert cell_lines == (
        "  Code   Qty",
        "> AAPL     5",
    )
    assert column_lines == (
        "  Code   Qty",
        "  AAPL     5",
    )
    assert cell_result.cursor == CursorDeclaration(row=1, column=11)
    assert column_result.cursor == CursorDeclaration(row=0, column=9)


def test_data_grid_cell_cursor_tracks_visible_start_for_right_aligned_values() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code", width=5), DataGridColumn("qty", "Qty", width=5, align="right")],
        [DataGridRow("line", {"code": "A1", "qty": 2})],
        active_row_key="line",
        active_column_key="qty",
        cursor_mode="cell",
        focused=True,
    )

    result = grid.render(RenderConstraints(width=18, max_height=3))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert lines[1] == "> A1         2"
    assert result.cursor == CursorDeclaration(row=1, column=lines[1].index("2"))


def test_data_grid_renders_row_labels_pinned_rows_and_body_viewport() -> None:
    grid = DataGrid(
        [DataGridColumn("qty", "Qty", width=3, align="right")],
        [
            DataGridRow("top", {"qty": 99}, label="Top", pinned="top"),
            *[DataGridRow(f"r{index}", {"qty": index}, label=f"R{index}") for index in range(6)],
            DataGridRow("total", {"qty": 15}, label="Total", pinned="bottom"),
        ],
        active_row_key="r5",
        show_row_labels=True,
        focused=True,
        wrap_rows=False,
    )

    result = grid.render(RenderConstraints(width=18, max_height=5))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert lines == (
        "         Qty",
        "  Top     99",
        "  R4       4",
        "> R5       5",
        "  Total   15",
    )
    assert result.cursor == CursorDeclaration(row=3, column=0)


def test_data_grid_fixed_columns_keep_identity_while_horizontal_window_tracks_active_column() -> None:
    grid = DataGrid(
        [
            DataGridColumn("id", "ID", width=3),
            DataGridColumn("name", "Name", width=6),
            DataGridColumn("note", "Note", width=6),
            DataGridColumn("owner", "Owner", width=5),
        ],
        [DataGridRow("a", {"id": "A1", "name": "Alpha", "note": "Queued", "owner": "Mina"})],
        active_row_key="a",
        active_column_key="owner",
        cursor_mode="cell",
        fixed_columns=1,
        focused=True,
    )

    lines = plain_lines(grid, width=18, height=3)

    assert lines == (
        "  ID   Owner",
        "> A1   Mina",
    )
    assert "Name" not in "\n".join(lines)
    assert "Note" not in "\n".join(lines)


def test_data_grid_theme_tokens_and_width_constraints_are_applied() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.dataGrid.header": {"color": "cyan"},
            "widget.dataGrid.row": {"color": "white"},
            "widget.dataGrid.rowAlternate": {"color": "bright_black"},
            "widget.dataGrid.focusRow": {"bold": True, "color": "green"},
            "widget.dataGrid.disabled": {"dim": True},
            "widget.dataGrid.positive": {"color": "green"},
        }
    )
    grid = DataGrid(
        [
            DataGridColumn("name", "Name", width=8),
            DataGridColumn(
                "delta",
                "Delta",
                width=6,
                align="right",
                formatter=DeltaFormatter(precision=1),
                theme_token_for_value=lambda value: "widget.dataGrid.positive" if value > 0 else None,
            ),
        ],
        [
            DataGridRow("build", {"name": "Build", "delta": 1.2}),
            DataGridRow("skip", {"name": "Skip", "delta": 0}, disabled=True),
        ],
        active_row_key="build",
        focused=True,
        zebra_stripes=True,
        theme=theme,
    )

    raw = render_lines(grid, width=20, height=3)
    plain = tuple(strip_control_sequences(line).rstrip() for line in raw)

    assert raw[0].startswith("\x1b[36m  Name")
    assert raw[1].startswith("\x1b[1;32m> Build")
    assert raw[2].startswith("\x1b[2m  Skip")
    assert plain == (
        "  Name       Delta",
        "> Build       +1.2",
        "  Skip         0.0",
    )
    assert all(visible_width(line) <= 20 for line in raw)


def test_data_grid_editable_cells_use_cell_level_theme_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.dataGrid.row": {"color": "white"},
            "widget.dataGrid.focusRow": {"color": "cyan"},
            "widget.dataGrid.editable": {"color": "yellow"},
            "widget.dataGrid.focusEditable": {"reverse": True},
        }
    )
    grid = DataGrid(
        [
            DataGridColumn("code", "Code", width=5, editable=True),
            DataGridColumn("name", "Name", width=7),
            DataGridColumn("qty", "Qty", width=5, align="right", editable=True),
        ],
        [DataGridRow("line", {"code": "A100", "name": "Adapter", "qty": 2})],
        active_column_key="qty",
        cursor_mode="cell",
        focused=True,
        theme=theme,
    )

    raw = render_lines(grid, width=28, height=3)
    body = raw[1]

    assert strip_control_sequences(body).rstrip() == "> A100   Adapter      2"
    assert "\x1b[33mA100 " in body
    assert "\x1b[7m    2" in body
    assert "\x1b[33mAdapter" not in body
    assert "\x1b[7mAdapter" not in body


def test_data_grid_activation_returns_callbacks_or_structured_targets() -> None:
    calls: list[str] = []
    row_grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [
            DataGridRow("build", {"job": "Build"}, on_select=lambda: calls.append("build")),
            DataGridRow("deploy", {"job": "Deploy"}),
        ],
    )
    cell_grid = DataGrid(
        [DataGridColumn("job", "Job"), DataGridColumn("runs", "Runs")],
        [DataGridRow("build", {"job": "Build", "runs": 12})],
        active_column_key="runs",
        cursor_mode="cell",
    )
    column_grid = DataGrid(
        [DataGridColumn("job", "Job"), DataGridColumn("runs", "Runs")],
        [DataGridRow("build", {"job": "Build", "runs": 12})],
        active_column_key="runs",
        cursor_mode="column",
    )
    none_grid = DataGrid([DataGridColumn("job", "Job")], [{"job": "Build"}], cursor_mode="none")

    assert row_grid.handle_input(InputEvent(kind="key", key="enter")) is True
    assert calls == ["build"]
    assert row_grid.handle_input(InputEvent(kind="key", key="down")) is True
    assert row_grid.handle_input(InputEvent(kind="key", key="enter")) == DataGridSelect(
        row_key="deploy",
        column_key=None,
        value=None,
        cursor_mode="row",
    )
    assert cell_grid.handle_input(InputEvent(kind="key", key="enter")) == DataGridSelect(
        row_key="build",
        column_key="runs",
        value=12,
        cursor_mode="cell",
    )
    assert column_grid.handle_input(InputEvent(kind="key", key="enter")) == DataGridSelect(
        row_key=None,
        column_key="runs",
        value=None,
        cursor_mode="column",
    )
    assert none_grid.handle_input(InputEvent(kind="key", key="enter")) is None


def test_data_grid_activate_row_sets_active_row_and_repairs_cell_column() -> None:
    row_grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [
            DataGridRow("summary", {"job": "Summary"}, pinned="top"),
            DataGridRow("build", {"job": "Build"}),
            DataGridRow("skip", {"job": "Skip"}, disabled=True),
            DataGridRow("deploy", {"job": "Deploy"}),
        ],
    )

    assert row_grid.activate_row("deploy") is True
    assert row_grid.active_row_key == "deploy"
    assert row_grid.activate_row("deploy") is False
    assert row_grid.activate_row("summary") is False
    assert row_grid.activate_row("skip") is False
    assert row_grid.activate_row("missing") is False

    cell_grid = DataGrid(
        [DataGridColumn("code", "Code", editable=True), DataGridColumn("qty", "Qty")],
        [
            DataGridRow("a", {"code": "A", "qty": 1}),
            DataGridRow("b", {"code": "B", "qty": DataGridCell(2, disabled=True)}),
        ],
        active_column_key="qty",
        cursor_mode="cell",
    )

    assert cell_grid.start_edit("a", "code") is True
    assert cell_grid.activate_row("b") is True
    assert (cell_grid.active_row_key, cell_grid.active_column_key) == ("b", "code")
    assert cell_grid.editing_cell_key is None


def test_data_grid_single_selection_replaces_row_or_cell_targets() -> None:
    row_grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [DataGridRow("build", {"job": "Build"}), DataGridRow("deploy", {"job": "Deploy"})],
        selection_mode="single",
    )
    cell_grid = DataGrid(
        [DataGridColumn("job", "Job"), DataGridColumn("runs", "Runs")],
        [DataGridRow("build", {"job": "Build", "runs": 12})],
        active_column_key="runs",
        cursor_mode="cell",
        selection_mode="single",
    )

    row_result = row_grid.handle_input(InputEvent(kind="key", key="space"))
    assert row_result == DataGridSelectionChange(frozenset({"build"}), frozenset())
    assert row_grid.selected_row_keys == frozenset({"build"})
    assert row_grid.handle_input(InputEvent(kind="text", text=" ")) is False
    assert row_grid.handle_input(InputEvent(kind="key", key="down")) is True
    assert row_grid.handle_input(InputEvent(kind="key", key="space")) == DataGridSelectionChange(
        frozenset({"deploy"}),
        frozenset(),
    )

    cell_result = cell_grid.handle_input(InputEvent(kind="key", key="space"))
    assert cell_result == DataGridSelectionChange(frozenset(), frozenset({("build", "runs")}))
    assert cell_grid.selected_cell_keys == frozenset({("build", "runs")})


def test_data_grid_multi_selection_and_select_all_skip_disabled_targets() -> None:
    grid = DataGrid(
        [DataGridColumn("job", "Job"), DataGridColumn("runs", "Runs")],
        [
            DataGridRow("build", {"job": "Build", "runs": 12}),
            DataGridRow("skip", {"job": "Skip", "runs": 0}, disabled=True),
            DataGridRow("deploy", {"job": "Deploy", "runs": DataGridCell(3, disabled=True)}),
            DataGridRow("release", {"job": "Release", "runs": 4}),
        ],
        active_column_key="runs",
        cursor_mode="column",
        selection_mode="multi",
    )
    single_column = DataGrid(
        [DataGridColumn("job", "Job"), DataGridColumn("runs", "Runs")],
        [DataGridRow("build", {"job": "Build", "runs": 12})],
        active_column_key="runs",
        cursor_mode="column",
        selection_mode="single",
    )

    assert single_column.handle_input(InputEvent(kind="key", key="space")) is False
    result = grid.handle_input(InputEvent(kind="key", key="space"))

    assert result == DataGridSelectionChange(
        frozenset(),
        frozenset({("build", "runs"), ("release", "runs")}),
    )
    assert grid.selected_cell_keys == frozenset({("build", "runs"), ("release", "runs")})

    row_grid = DataGrid(
        [DataGridColumn("job", "Job")],
        [
            DataGridRow("build", {"job": "Build"}),
            DataGridRow("skip", {"job": "Skip"}, disabled=True),
            DataGridRow("deploy", {"job": "Deploy"}),
        ],
        selection_mode="multi",
    )
    assert row_grid.select_all() is True
    assert row_grid.selected_row_keys == frozenset({"build", "deploy"})
    assert row_grid.clear_selection() is True
    assert row_grid.selected_row_keys == frozenset()


def test_data_grid_editing_replaces_initial_buffer_and_commits_parsed_values() -> None:
    grid = DataGrid(
        [
            DataGridColumn("code", "Code", editable=True),
            DataGridColumn("qty", "Qty", editable=True, parser=int),
        ],
        [DataGridRow("line", {"code": "AAPL", "qty": 1})],
        cursor_mode="cell",
        active_column_key="code",
    )

    assert grid.handle_input(InputEvent(kind="key", key="e")) is True
    assert grid.editing_cell_key == ("line", "code")
    assert grid.handle_input(InputEvent(kind="text", text="M")) is True
    assert grid.handle_input(InputEvent(kind="text", text="SFT")) is True
    assert grid.handle_input(InputEvent(kind="key", key="enter")) == DataGridEdit("line", "code", "AAPL", "MSFT")
    assert grid.cell_value("line", "code") == "MSFT"
    assert grid.editing_cell_key is None

    assert grid.handle_input(InputEvent(kind="key", key="right")) is True
    assert grid.handle_input(InputEvent(kind="key", key="e")) is True
    assert grid.handle_input(InputEvent(kind="key", key="backspace")) is True
    assert grid.handle_input(InputEvent(kind="text", text="12")) is True
    assert grid.handle_input(InputEvent(kind="key", key="enter")) == DataGridEdit("line", "qty", 1, 12)
    assert grid.cell_value("line", "qty") == 12


def test_data_grid_printable_text_starts_editing_and_cursor_tracks_buffer_end() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code", width=8, editable=True)],
        [DataGridRow("line", {"code": ""})],
        cursor_mode="cell",
        active_column_key="code",
        focused=True,
    )

    assert grid.handle_input(InputEvent(kind="text", text="C100")) is True
    assert grid.editing_cell_key == ("line", "code")
    result = grid.render(RenderConstraints(width=16, max_height=3))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert lines[1] == "> C100"
    assert result.cursor == CursorDeclaration(row=1, column=6)


def test_data_grid_editing_arrow_keys_move_text_cursor_without_leaving_cell() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code", width=8, editable=True), DataGridColumn("qty", "Qty", editable=True)],
        [DataGridRow("line", {"code": "", "qty": 1})],
        cursor_mode="cell",
        active_column_key="code",
    )

    assert grid.handle_input(InputEvent(kind="text", text="C100")) is True
    assert grid.handle_input(InputEvent(kind="key", key="left")) is True
    assert grid.handle_input(InputEvent(kind="key", key="left")) is True
    assert grid.handle_input(InputEvent(kind="text", text="X")) is True
    assert grid.handle_input(InputEvent(kind="key", key="up")) is False
    assert (grid.active_row_key, grid.active_column_key) == ("line", "code")
    assert grid.editing_cell_key == ("line", "code")

    assert grid.handle_input(InputEvent(kind="key", key="enter")) == DataGridEdit("line", "code", "", "C1X00")
    assert grid.cell_value("line", "code") == "C1X00"


def test_data_grid_right_aligned_cells_edit_left_aligned_so_cursor_tracks_typing() -> None:
    grid = DataGrid(
        [DataGridColumn("qty", "Qty", width=5, align="right", editable=True, parser=int)],
        [DataGridRow("line", {"qty": 1})],
        cursor_mode="cell",
        focused=True,
    )

    assert grid.start_edit("line", "qty") is True
    assert grid.handle_input(InputEvent(kind="text", text="3")) is True
    one_digit = grid.render(RenderConstraints(width=12, max_height=3))
    one_digit_lines = tuple(strip_control_sequences(line.text).rstrip() for line in one_digit.lines)

    assert one_digit_lines[1] == "> 3"
    assert one_digit.cursor == CursorDeclaration(row=1, column=one_digit_lines[1].index("3") + 1)

    assert grid.handle_input(InputEvent(kind="text", text="2")) is True
    two_digits = grid.render(RenderConstraints(width=12, max_height=3))
    two_digit_lines = tuple(strip_control_sequences(line.text).rstrip() for line in two_digits.lines)

    assert two_digit_lines[1] == "> 32"
    assert two_digits.cursor == CursorDeclaration(row=1, column=two_digit_lines[1].index("32") + 2)
    assert two_digits.cursor.column == one_digit.cursor.column + 1


def test_data_grid_enter_to_edit_accepts_defaults_and_advances_to_next_column() -> None:
    grid = DataGrid(
        [
            DataGridColumn("code", "Code", editable=True, enter_behavior="edit", edit_next_column_key="qty"),
            DataGridColumn("qty", "Qty", editable=True, parser=int),
        ],
        [DataGridRow("line", {"code": "", "qty": 1})],
        cursor_mode="cell",
        active_column_key="code",
    )

    assert grid.handle_input(InputEvent(kind="key", key="enter")) is True
    assert grid.editing_cell_key == ("line", "code")
    assert grid.handle_input(InputEvent(kind="text", text="AAPL")) is True
    assert grid.handle_input(InputEvent(kind="key", key="enter")) == DataGridEdit("line", "code", "", "AAPL")
    assert grid.editing_cell_key == ("line", "qty")
    assert grid.handle_input(InputEvent(kind="key", key="enter")) == DataGridEdit("line", "qty", 1, 1)
    assert grid.editing_cell_key is None
    assert grid.cell_value("line", "qty") == 1


def test_data_grid_editing_keeps_errors_open_and_escape_cancels() -> None:
    grid = DataGrid(
        [
            DataGridColumn(
                "qty",
                "Qty",
                editable=True,
                parser=int,
                validator=lambda value: "must be positive" if value <= 0 else None,
            )
        ],
        [DataGridRow("line", {"qty": 5})],
        cursor_mode="cell",
    )

    assert grid.start_edit("line", "qty") is True
    assert grid.handle_input(InputEvent(kind="text", text="0")) is True
    assert grid.handle_input(InputEvent(kind="key", key="enter")) is None
    assert grid.editing_cell_key == ("line", "qty")
    assert grid.editing_error == "must be positive"
    assert grid.cell_value("line", "qty") == 5
    assert grid.handle_input(InputEvent(kind="key", key="escape")) is True
    assert grid.editing_cell_key is None
    assert grid.editing_error is None


def test_data_grid_sort_by_and_clear_sort_are_stable() -> None:
    grid = DataGrid(
        [DataGridColumn("name", "Name"), DataGridColumn("qty", "Qty")],
        [
            DataGridRow("a", {"name": "Alpha", "qty": 2}),
            DataGridRow("b", {"name": "Beta", "qty": 1}),
            DataGridRow("c", {"name": "Charlie", "qty": 2}),
        ],
    )

    assert grid.sort_by("qty", direction="asc") is True
    assert grid.sort_state == ("qty", "asc")
    assert grid.row_keys == ("b", "a", "c")
    assert grid.sort_by("qty", direction="desc") is True
    assert grid.row_keys == ("a", "c", "b")
    assert grid.clear_sort() is True
    assert grid.sort_state is None
    assert grid.row_keys == ("a", "b", "c")
    assert grid.sort_by("missing") is False


def test_data_grid_replace_rows_preserves_explicit_keys_and_rekeys_shorthand_rows() -> None:
    grid = DataGrid(
        [DataGridColumn("name", "Name"), DataGridColumn("qty", "Qty")],
        [
            DataGridRow("a", {"name": "Alpha", "qty": 2}),
            DataGridRow("b", {"name": "Beta", "qty": 1}),
            DataGridRow("c", {"name": "Charlie", "qty": 3}),
        ],
        active_row_key="c",
        selection_mode="multi",
    )
    assert grid.select_row("b") is True
    assert grid.sort_by("qty") is True

    grid.replace_rows(
        [
            DataGridRow("b", {"name": "Beta", "qty": 5}),
            DataGridRow("c", {"name": "Charlie", "qty": 0}),
        ]
    )

    assert grid.row_keys == ("c", "b")
    assert grid.active_row_key == "c"
    assert grid.selected_row_keys == frozenset({"b"})

    shorthand = DataGrid([DataGridColumn("name", "Name")], [{"name": "Old"}])
    assert shorthand.row_keys == ("row-0",)
    shorthand.replace_rows([{"name": "New"}])
    assert shorthand.row_keys == ("row-1",)


def test_data_grid_mutation_apis_repair_state_and_selection() -> None:
    grid = DataGrid(
        [DataGridColumn("name", "Name"), DataGridColumn("qty", "Qty", editable=True, parser=int)],
        [DataGridRow("build", {"name": "Build", "qty": 1})],
        cursor_mode="cell",
        selection_mode="multi",
    )

    new_key = grid.add_row({"name": "Deploy", "qty": 3}, activate=True, edit_column_key="qty")
    assert new_key == "row-0"
    assert grid.active_row_key == "row-0"
    assert grid.editing_cell_key == ("row-0", "qty")
    assert grid.update_cell("row-0", "qty", 4) is True
    assert grid.cell_value("row-0", "qty") == 4
    assert grid.editing_cell_key is None

    assert grid.add_column(DataGridColumn("status", "Status"), default=DataGridCell("ready", disabled=True)) is True
    assert grid.cell_value("build", "status") == "ready"
    assert grid.cell_disabled("build", "status") is True
    assert grid.select_cell("build", "name") is True
    assert grid.remove_column("name") is True
    assert grid.selected_cell_keys == frozenset()
    assert grid.active_column_key == "qty"

    assert grid.remove_row("row-0") is True
    assert grid.active_row_key == "build"
    grid.clear()
    assert grid.row_keys == ()
    assert grid.active_row_key is None
    assert grid.selected_row_keys == frozenset()
    assert grid.sort_state is None


def test_data_grid_column_visibility_controls_repair_active_state_and_selection() -> None:
    grid = DataGrid(
        [
            DataGridColumn("code", "Code"),
            DataGridColumn("qty", "Qty", editable=True, parser=int),
            DataGridColumn("note", "Note"),
        ],
        [DataGridRow("line", {"code": "A1", "qty": 2, "note": "ready"})],
        active_column_key="qty",
        cursor_mode="cell",
        selection_mode="multi",
    )
    grid.focus()

    assert grid.select_cell("line", "qty") is True
    assert grid.start_edit("line", "qty") is True
    assert grid.set_column_hidden("qty") is True

    assert tuple(column.hidden for column in grid.columns) == (False, True, False)
    assert grid.active_column_key == "code"
    assert grid.selected_cell_keys == frozenset()
    assert grid.editing_cell_key is None
    assert grid.sort_by("qty") is False
    assert "Qty" not in "\n".join(plain_lines(grid, width=48, height=4))

    assert grid.set_column_hidden("qty", False) is True
    assert tuple(column.hidden for column in grid.columns) == (False, False, False)
    assert grid.toggle_column("qty") is True
    assert tuple(column.hidden for column in grid.columns) == (False, True, False)
    assert grid.toggle_column("missing") is False


def test_data_grid_hiding_all_columns_renders_empty_text() -> None:
    grid = DataGrid(
        [DataGridColumn("code", "Code"), DataGridColumn("qty", "Qty")],
        [DataGridRow("line", {"code": "A1", "qty": 2})],
        active_column_key="qty",
        cursor_mode="cell",
        empty_text="No visible columns",
    )

    assert grid.set_column_hidden("code") is True
    assert grid.set_column_hidden("qty") is True

    assert grid.active_column_key is None
    assert plain_lines(grid, width=40, height=4) == ("No visible columns",)


def test_data_grid_move_column_preserves_data_and_active_column_key() -> None:
    grid = DataGrid(
        [
            DataGridColumn("symbol", "Symbol"),
            DataGridColumn("price", "Price"),
            DataGridColumn("change", "Change"),
        ],
        [DataGridRow("aapl", {"symbol": "AAPL", "price": 213.41, "change": 2.18})],
        active_column_key="price",
        cursor_mode="column",
        fixed_columns=1,
    )

    assert grid.move_column("change", index=0) is True
    assert tuple(column.key for column in grid.columns) == ("change", "symbol", "price")
    assert grid.active_column_key == "price"
    assert grid.cell_value("aapl", "price") == 213.41

    assert grid.move_column("price", before="symbol") is True
    assert tuple(column.key for column in grid.columns) == ("change", "price", "symbol")
    assert grid.move_column("change", after="symbol") is True
    assert tuple(column.key for column in grid.columns) == ("price", "symbol", "change")
    assert grid.move_column("missing", index=0) is False
    assert grid.move_column("price") is False


def test_data_grid_set_column_width_updates_and_unsets_fixed_width() -> None:
    grid = DataGrid(
        [DataGridColumn("symbol", "Symbol"), DataGridColumn("price", "Price", width=9, align="right")],
        [DataGridRow("aapl", {"symbol": "AAPL", "price": 213.41})],
    )

    assert grid.set_column_width("price", 4) is True
    assert tuple(column.width for column in grid.columns) == (None, 4)
    assert grid.set_column_width("price", 4) is False
    assert grid.set_column_width("price", -2) is True
    assert tuple(column.width for column in grid.columns) == (None, 0)
    assert grid.set_column_width("price", None) is True
    assert tuple(column.width for column in grid.columns) == (None, None)
    assert grid.set_column_width("missing", 8) is False


def test_data_grid_large_viewport_formats_only_visible_rows() -> None:
    formatted: list[int] = []

    def counted_formatter(value: object) -> str:
        formatted.append(int(value))
        return f"Item {value}"

    grid = DataGrid(
        [DataGridColumn("name", "Name", formatter=counted_formatter)],
        [DataGridRow(str(index), {"name": index}) for index in range(10_000)],
        active_row_key="9999",
    )

    lines = plain_lines(grid, width=24, height=4)

    assert any("Item 9999" in line for line in lines)
    assert formatted == [9997, 9998, 9999]


def test_widgets_datagrid_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/58_widgets_datagrid.py", run_name="__test__")

    build_app = namespace["build_app"]
    app = build_app()
    result = app.render(RenderConstraints(width=96, max_height=24))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert callable(build_app)
    assert "DataGrid examples" in lines[0]
    assert any("Market watchlist" in line for line in lines)
    assert any("AAPL" in line for line in lines)


def test_widgets_datagrid_adapter_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/59_widgets_datagrid_adapters.py", run_name="__test__")

    build_app = namespace["build_app"]
    app = build_app()
    result = app.render(RenderConstraints(width=96, max_height=20))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert callable(build_app)
    assert "DataGrid adapter examples" in lines[0]
    assert any("Records" in line for line in lines)
    assert any("AAPL" in line for line in lines)


def test_widgets_datagrid_large_dataset_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/60_widgets_datagrid_large_dataset.py", run_name="__test__")

    build_app = namespace["build_app"]
    app = build_app()
    result = app.render(RenderConstraints(width=100, max_height=24))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert callable(build_app)
    assert "Large DataGrid" in lines[0]
    assert any("2,000 rows" in line for line in lines)
    assert any("Go to page" in line for line in lines)
    assert any("Rows 1-" in line for line in lines)


def test_widgets_datagrid_large_dataset_go_to_page() -> None:
    namespace = runpy.run_path("examples/tui/60_widgets_datagrid_large_dataset.py", run_name="__test__")

    app = namespace["LargeDataGridExampleApp"]()
    app.render(RenderConstraints(width=100, max_height=24))
    page_size = app.page_size

    assert app.handle_input(InputEvent(kind="key", key="ctrl+g")) is True
    assert app.handle_input(InputEvent(kind="text", text="10")) is True
    assert app.handle_input(InputEvent(kind="key", key="enter")) is True

    assert app.grid.active_row_key == f"row-{(10 - 1) * page_size}"
    assert app.focus_region == "grid"
    assert "Page 10/" in app.status


def test_widgets_datagrid_large_dataset_invalid_page_stays_in_input() -> None:
    namespace = runpy.run_path("examples/tui/60_widgets_datagrid_large_dataset.py", run_name="__test__")

    app = namespace["LargeDataGridExampleApp"]()
    app.render(RenderConstraints(width=100, max_height=24))

    assert app.handle_input(InputEvent(kind="key", key="ctrl+g")) is True
    assert app.handle_input(InputEvent(kind="text", text="abc")) is True
    assert app.handle_input(InputEvent(kind="key", key="enter")) is True

    assert app.grid.active_row_key == "row-0"
    assert app.focus_region == "goto"
    assert app.status == "Invalid page"


def test_widgets_datagrid_large_dataset_focus_shortcuts_and_input_width() -> None:
    namespace = runpy.run_path("examples/tui/60_widgets_datagrid_large_dataset.py", run_name="__test__")

    app = namespace["LargeDataGridExampleApp"]()
    result = app.render(RenderConstraints(width=100, max_height=24))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert app.handle_input(InputEvent(kind="text", text="g")) is None
    assert app.focus_region == "grid"
    assert "  Go to page: [1   ] / 106" in lines[1]
    assert "g page" not in lines[-1]

    assert app.handle_input(InputEvent(kind="key", key="ctrl_g")) is True
    result = app.render(RenderConstraints(width=100, max_height=24))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)
    assert app.focus_region == "goto"
    assert lines[1].startswith("> Go to page:")

    assert app.handle_input(InputEvent(kind="key", key="tab")) is True
    assert app.focus_region == "grid"
    assert app.handle_input(InputEvent(kind="key", key="tab")) is True
    assert app.focus_region == "goto"

    assert app.handle_input(InputEvent(kind="text", text="106")) is True
    result = app.render(RenderConstraints(width=100, max_height=24))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)
    assert "> Go to page: [106 ] / 106" in lines[1]


def test_widgets_datagrid_adapter_example_column_controls() -> None:
    namespace = runpy.run_path("examples/tui/59_widgets_datagrid_adapters.py", run_name="__test__")

    app = namespace["DataGridAdapterExampleApp"]()
    grid = app.active_scenario.grid

    assert app.handle_input(InputEvent(kind="text", text="v")) is True
    assert next(column for column in grid.columns if column.key == "change_pct").hidden is True
    assert "Change %" not in "\n".join(plain_lines(grid, width=72, height=8))

    assert app.handle_input(InputEvent(kind="text", text="]")) is True
    assert next(column for column in grid.columns if column.key == "price").width == 10

    assert app.handle_input(InputEvent(kind="text", text=".")) is True
    assert tuple(column.key for column in grid.columns) == ("symbol", "change", "price", "change_pct")


def test_widgets_datagrid_adapter_example_playback_switches_sources() -> None:
    frames = play_example(
        "examples/tui/59_widgets_datagrid_adapters.py",
        events=(
            ("json", InputEvent(kind="key", key="down")),
            ("csv", InputEvent(kind="key", key="down")),
        ),
        width=104,
        height=20,
    )

    assert any("Records" in line for line in frames[0].lines)
    assert any("AAPL" in line for line in frames[0].lines)
    assert any("JSON" in line for line in frames[1].lines)
    assert any("Deploy" in line for line in frames[1].lines)
    assert any("CSV" in line for line in frames[2].lines)
    assert any("MSFT" in line for line in frames[2].lines)


def test_widgets_datagrid_example_playback_switches_scenarios() -> None:
    frames = play_example(
        "examples/tui/58_widgets_datagrid.py",
        events=(
            ("order", InputEvent(kind="key", key="down")),
            ("jobs", InputEvent(kind="key", key="down")),
            ("usage", InputEvent(kind="key", key="down")),
            ("diagnostics", InputEvent(kind="key", key="down")),
        ),
        width=104,
        height=24,
    )

    assert any("Market watchlist" in line for line in frames[0].lines)
    assert any("Order entry" in line for line in frames[1].lines)
    assert any("Total" in line for line in frames[1].lines)
    assert any("Job status" in line for line in frames[2].lines)
    assert any("Token usage" in line for line in frames[3].lines)
    assert any("Diagnostics" in line for line in frames[4].lines)


def test_widgets_datagrid_example_routes_text_to_grid_after_entering_right_pane() -> None:
    frames = play_example(
        "examples/tui/58_widgets_datagrid.py",
        events=(
            ("order", InputEvent(kind="key", key="down")),
            ("enter grid", InputEvent(kind="key", key="enter")),
            ("edit code", InputEvent(kind="key", key="enter")),
            ("type A", InputEvent(kind="text", text="A")),
            ("type 1", InputEvent(kind="text", text="1")),
        ),
        width=104,
        height=24,
    )

    assert any("Order entry" in line for line in frames[-1].lines)
    assert any("A1" in line for line in frames[-1].lines)
    assert any("* 2 Order entry" in line for line in frames[-1].lines)
    assert not any("AAPL" in line for line in frames[-1].lines)


def test_widgets_datagrid_example_q_text_does_not_quit_while_editing_cell() -> None:
    namespace = runpy.run_path("examples/tui/58_widgets_datagrid.py", run_name="__test__")
    app = namespace["DataGridExampleApp"]()
    should_quit = namespace["_should_quit"]

    assert should_quit(InputEvent(kind="text", text="q"), app) is True

    app.handle_input(InputEvent(kind="key", key="down"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    assert app.active_scenario.grid.editing_cell_key == ("line-2", "code")

    assert should_quit(InputEvent(kind="text", text="q"), app) is False
    assert should_quit(InputEvent(kind="key", key="ctrl+c"), app) is True


def test_widgets_datagrid_example_qty_error_is_visible_and_clears_after_success() -> None:
    namespace = runpy.run_path("examples/tui/58_widgets_datagrid.py", run_name="__test__")
    app = namespace["DataGridExampleApp"]()

    app.handle_input(InputEvent(kind="key", key="down"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    grid = app.active_scenario.grid

    app.handle_input(InputEvent(kind="text", text="C300"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    assert grid.editing_cell_key == ("line-2", "qty")

    app.handle_input(InputEvent(kind="text", text="q"))
    app.handle_input(InputEvent(kind="key", key="enter"))

    lines = plain_lines(app, width=120, height=24)
    raw_lines = render_lines(app, width=120, height=24)
    assert grid.editing_cell_key == ("line-2", "qty")
    assert grid.editing_error == "Qty must be a whole number"
    assert any("Error: Qty must be a whole number" in line for line in lines)
    assert any("\x1b[31m" in line and "Error: Qty must be a whole number" in line for line in raw_lines)

    app.handle_input(InputEvent(kind="key", key="backspace"))
    app.handle_input(InputEvent(kind="text", text="3"))
    app.handle_input(InputEvent(kind="key", key="enter"))

    lines = plain_lines(app, width=120, height=24)
    assert grid.editing_cell_key is None
    assert grid.editing_error is None
    assert not any("Error:" in line for line in lines)
    assert grid.cell_value("line-2", "qty") == 3


def test_widgets_datagrid_example_order_entry_lookup_total_and_adds_next_line() -> None:
    namespace = runpy.run_path("examples/tui/58_widgets_datagrid.py", run_name="__test__")
    app = namespace["DataGridExampleApp"]()

    app.handle_input(InputEvent(kind="key", key="down"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="key", key="down"))
    assert app.active_scenario.key == "2"
    grid = app.active_scenario.grid
    assert (grid.active_row_key, grid.active_column_key) == ("line-2", "code")

    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="text", text="C300"))
    app.handle_input(InputEvent(kind="key", key="enter"))

    assert grid.cell_value("line-2", "name") == "Clamp"
    assert grid.cell_value("line-2", "price") == 7.25
    assert grid.editing_cell_key == ("line-2", "qty")

    app.handle_input(InputEvent(kind="key", key="enter"))

    assert grid.row_keys == ("line-1", "line-2", "line-3", "total")
    assert grid.editing_cell_key is None
    assert (grid.active_row_key, grid.active_column_key) == ("line-3", "code")
    app.handle_input(InputEvent(kind="key", key="up"))
    assert (grid.active_row_key, grid.active_column_key) == ("line-2", "code")
    assert grid.cell_value("line-2", "total") == 7.25
    assert grid.cell_value("total", "total") == 46.25


def test_widgets_datagrid_example_deletes_order_rows_from_navigation_state() -> None:
    namespace = runpy.run_path("examples/tui/58_widgets_datagrid.py", run_name="__test__")
    app = namespace["DataGridExampleApp"]()

    app.handle_input(InputEvent(kind="key", key="down"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    grid = app.active_scenario.grid
    assert (grid.active_row_key, grid.active_column_key) == ("line-2", "code")

    app.handle_input(InputEvent(kind="text", text="C300"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="key", key="up"))
    app.handle_input(InputEvent(kind="key", key="delete"))

    assert grid.row_keys == ("line-1", "line-3", "total")
    assert (grid.active_row_key, grid.active_column_key) == ("line-3", "code")
    assert grid.cell_value("total", "total") == 39.0


def test_widgets_datagrid_example_backspace_does_not_delete_order_rows_from_navigation_state() -> None:
    namespace = runpy.run_path("examples/tui/58_widgets_datagrid.py", run_name="__test__")
    app = namespace["DataGridExampleApp"]()

    app.handle_input(InputEvent(kind="key", key="down"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    grid = app.active_scenario.grid

    app.handle_input(InputEvent(kind="text", text="C300"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="key", key="up"))
    app.handle_input(InputEvent(kind="key", key="backspace"))

    assert grid.row_keys == ("line-1", "line-2", "line-3", "total")
    assert grid.cell_value("total", "total") == 46.25


def test_widgets_datagrid_example_ctrl_d_deletes_order_rows_from_navigation_state() -> None:
    namespace = runpy.run_path("examples/tui/58_widgets_datagrid.py", run_name="__test__")
    app = namespace["DataGridExampleApp"]()

    app.handle_input(InputEvent(kind="key", key="down"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    grid = app.active_scenario.grid

    app.handle_input(InputEvent(kind="text", text="C300"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    app.handle_input(InputEvent(kind="key", key="up"))
    app.handle_input(InputEvent(kind="key", key="ctrl+d"))

    assert grid.row_keys == ("line-1", "line-3", "total")
    assert (grid.active_row_key, grid.active_column_key) == ("line-3", "code")
    assert grid.cell_value("total", "total") == 39.0


def test_widgets_datagrid_example_delete_last_order_row_focuses_previous_row() -> None:
    namespace = runpy.run_path("examples/tui/58_widgets_datagrid.py", run_name="__test__")
    app = namespace["DataGridExampleApp"]()

    app.handle_input(InputEvent(kind="key", key="down"))
    app.handle_input(InputEvent(kind="key", key="enter"))
    grid = app.active_scenario.grid
    assert (grid.active_row_key, grid.active_column_key) == ("line-2", "code")

    app.handle_input(InputEvent(kind="key", key="delete"))

    assert grid.row_keys == ("line-1", "total")
    assert (grid.active_row_key, grid.active_column_key) == ("line-1", "code")
    assert grid.cell_value("total", "total") == 39.0
