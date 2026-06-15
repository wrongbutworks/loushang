from __future__ import annotations

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
    DataGridRow,
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
    assert cell_result.cursor == CursorDeclaration(row=1, column=9)
    assert column_result.cursor == CursorDeclaration(row=0, column=9)


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
