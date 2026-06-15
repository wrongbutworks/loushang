from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    ColumnChooser,
    ColumnChooserClose,
    ColumnChooserColumn,
    ColumnChooserMove,
    ColumnChooserSelect,
    ColumnChooserSort,
    ColumnChooserToggle,
    ColumnChooserWidthChange,
    CursorDeclaration,
    DataGrid,
    DataGridColumn,
    DeltaFormatter,
    FocusableMixin,
    InputEvent,
    NumberFormatter,
    PercentFormatter,
    RenderConstraints,
    RenderLine,
    RenderResult,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    apply_theme_style,
    normalize_key_id,
    truncate_to_width,
    visible_width,
)

LEFT_WIDTH = 42

COLUMN_CHOOSER_THEME = ThemeResolver(
    defaults={
        "example.dataGrid.title": {"bold": True, "color": "cyan"},
        "example.dataGrid.panelTitle": {"bold": True, "color": "bright_black"},
        "example.dataGrid.meta": {"color": "bright_black"},
        "widget.columnChooser.row": {"color": "white"},
        "widget.columnChooser.focus": {"bold": True, "color": "cyan"},
        "widget.columnChooser.hidden": {"color": "bright_black"},
        "widget.columnChooser.disabled": {"dim": True},
        "widget.dataGrid.header": {"color": "bright_black"},
        "widget.dataGrid.row": {"color": "white"},
        "widget.dataGrid.focusCell": {"bold": True, "color": "cyan"},
        "widget.dataGrid.fixedColumn": {"color": "bright_white"},
        "widget.dataGrid.positive": {"color": "green"},
        "widget.dataGrid.negative": {"color": "red"},
        "widget.dataGrid.neutral": {"color": "bright_black"},
    }
)


@dataclass(slots=True)
class DataGridColumnChooserExampleApp(FocusableMixin):
    grid: DataGrid = field(default_factory=lambda: _records_grid())
    column_chooser: ColumnChooser = field(init=False)
    focus_region: str = "columns"
    status: str = "Column chooser"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.column_chooser = ColumnChooser(
            _column_chooser_columns(self.grid),
            theme=COLUMN_CHOOSER_THEME,
            focused=True,
        )
        self.focus()

    def focus(self) -> None:
        self.focused = True
        self._focus_columns()

    def blur(self) -> None:
        self.focused = False
        self.grid.blur()
        self.column_chooser.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        height = min(constraints.max_height, constraints.visible_height or constraints.max_height)
        if height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        right_width = max(1, width - LEFT_WIDTH - 3)
        body_height = max(1, height - 4)
        chooser_result = self.column_chooser.render(RenderConstraints(width=LEFT_WIDTH, max_height=max(1, body_height - 1)))
        grid_result = self.grid.render(RenderConstraints(width=right_width, max_height=body_height))
        left_lines = [_style("Column chooser", "example.dataGrid.panelTitle")]
        left_lines.extend(line.text for line in chooser_result.lines)

        rows = [
            RenderLine(_style(truncate_to_width("DataGrid column chooser", max_width=width, ellipsis=""), "example.dataGrid.title")),
            RenderLine(""),
        ]
        for index in range(body_height):
            left = left_lines[index] if index < len(left_lines) else ""
            right = grid_result.lines[index].text if index < len(grid_result.lines) else ""
            rows.append(RenderLine(_combine(left, right, width=width)))
        rows.append(RenderLine(""))
        rows.append(RenderLine(_style(truncate_to_width(_footer(self), max_width=width, ellipsis=""), "example.dataGrid.meta")))

        cursor = None
        if self.focus_region == "columns" and chooser_result.cursor is not None:
            cursor = CursorDeclaration(row=3 + chooser_result.cursor.row, column=chooser_result.cursor.column)
        elif self.focus_region == "grid" and grid_result.cursor is not None:
            cursor = CursorDeclaration(row=2 + grid_result.cursor.row, column=LEFT_WIDTH + 3 + grid_result.cursor.column)
        return RenderResult.from_lines(rows[:height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        key = normalize_key_id(getattr(event, "key", "")) if getattr(event, "kind", "") == "key" else ""
        if key == "tab":
            self._focus_grid() if self.focus_region == "columns" else self._focus_columns()
            return True
        if self.focus_region == "columns":
            result = self.column_chooser.handle_input(event)
            return self._handle_column_chooser_result(result)
        if key == "escape":
            self._focus_columns()
            return True
        return self.grid.handle_input(event)

    def _handle_column_chooser_result(self, result: object) -> object:
        if isinstance(result, ColumnChooserToggle):
            self.grid.toggle_column(result.column_key)
            self._sync_column_chooser(active_key=result.column_key)
            column = _column_by_key(self.grid, result.column_key)
            state = "hidden" if column is not None and column.hidden else "visible"
            self.status = f"{_column_label(self.grid, result.column_key)} {state}"
            return True
        if isinstance(result, ColumnChooserWidthChange):
            column = _column_by_key(self.grid, result.column_key)
            if column is None:
                self.status = "Missing column"
                return True
            width = column.width if column.width is not None else 8
            self.grid.set_column_width(result.column_key, max(3, width + result.delta))
            self._sync_column_chooser(active_key=result.column_key)
            next_column = _column_by_key(self.grid, result.column_key)
            self.status = f"{_column_label(self.grid, result.column_key)} width {next_column.width if next_column else width}"
            return True
        if isinstance(result, ColumnChooserMove):
            moved = self._move_column(result.column_key, result.direction)
            self._sync_column_chooser(active_key=result.column_key)
            self.status = f"{_column_label(self.grid, result.column_key)} moved" if moved else "Column edge"
            return True
        if isinstance(result, ColumnChooserSort):
            changed = self.grid.cycle_sort(result.column_key)
            self._sync_column_chooser(active_key=result.column_key)
            self.status = _sort_status(self.grid) if changed else "Sort unchanged"
            return True
        if isinstance(result, ColumnChooserSelect):
            self._activate_grid_column(result.column_key)
            return True
        if isinstance(result, ColumnChooserClose):
            self._focus_grid()
            return True
        return result

    def _move_column(self, column_key: str, direction: str) -> bool:
        keys = [column.key for column in self.grid.columns]
        if column_key not in keys:
            return False
        position = keys.index(column_key)
        delta = -1 if direction == "up" else 1
        next_position = max(0, min(len(keys) - 1, position + delta))
        if next_position == position:
            return False
        target = keys[next_position]
        return (
            self.grid.move_column(column_key, before=target)
            if next_position < position
            else self.grid.move_column(column_key, after=target)
        )

    def _activate_grid_column(self, column_key: str) -> None:
        row_key = self.grid.active_row_key
        if row_key is not None:
            self.grid.activate_cell(row_key, column_key)
        self._focus_grid()
        self.status = f"Grid column {_column_label(self.grid, column_key)}"

    def _sync_column_chooser(self, *, active_key: str | None = None) -> None:
        self.column_chooser.set_columns(_column_chooser_columns(self.grid), active_key=active_key)

    def _focus_columns(self) -> None:
        self.focus_region = "columns"
        self.grid.blur()
        self.column_chooser.focus()

    def _focus_grid(self) -> None:
        self.focus_region = "grid"
        self.column_chooser.blur()
        if self.focused:
            self.grid.focus()


def build_app() -> Tui:
    tui = Tui()
    app = DataGridColumnChooserExampleApp()
    tui.add_child(app)
    tui.set_focus(app)
    return tui


async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if _should_quit(event):
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


def _records_grid() -> DataGrid:
    return DataGrid.from_records(
        (
            {"symbol": "AAPL", "price": 213.41, "change": 2.18, "change_pct": 0.0103},
            {"symbol": "MSFT", "price": 491.72, "change": -1.64, "change_pct": -0.0033},
            {"symbol": "NVDA", "price": 142.83, "change": 0.0, "change_pct": 0.0},
        ),
        columns=_market_columns(),
        row_key_field="symbol",
        cursor_mode="cell",
        fixed_columns=1,
        theme=COLUMN_CHOOSER_THEME,
        wrap_rows=False,
    )


def _market_columns() -> tuple[DataGridColumn, ...]:
    return (
        DataGridColumn("symbol", "Symbol", width=7),
        DataGridColumn("price", "Price", width=9, align="right", formatter=NumberFormatter(precision=2)),
        DataGridColumn(
            "change",
            "Change",
            width=8,
            align="right",
            formatter=DeltaFormatter(precision=2),
            theme_token_for_value=_delta_token,
        ),
        DataGridColumn(
            "change_pct",
            "Change %",
            width=9,
            align="right",
            formatter=PercentFormatter(precision=2, sign=True),
            theme_token_for_value=_delta_token,
        ),
    )


def _column_chooser_columns(grid: DataGrid) -> tuple[ColumnChooserColumn, ...]:
    return tuple(
        ColumnChooserColumn(
            key=column.key,
            label=column.header,
            visible=not column.hidden,
            width=column.width,
            fixed=index < grid.fixed_columns,
            sortable=not column.hidden,
        )
        for index, column in enumerate(grid.columns)
    )


def _delta_token(value: object) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 0:
        return "widget.dataGrid.positive"
    if number < 0:
        return "widget.dataGrid.negative"
    return "widget.dataGrid.neutral"


def _combine(left: str, right: str, *, width: int) -> str:
    left_text = truncate_to_width(left, max_width=LEFT_WIDTH, ellipsis="")
    padding = " " * max(0, LEFT_WIDTH - visible_width(left_text))
    return truncate_to_width(f"{left_text}{padding} | {right}", max_width=width, ellipsis="")


def _column_by_key(grid: DataGrid, key: str) -> DataGridColumn | None:
    for column in grid.columns:
        if column.key == key:
            return column
    return None


def _column_label(grid: DataGrid, key: str) -> str:
    column = _column_by_key(grid, key)
    return key if column is None else column.header


def _sort_status(grid: DataGrid) -> str:
    if grid.sort_state is None:
        return "Sort none"
    column_key, direction = grid.sort_state
    return f"Sort {_column_label(grid, column_key)} {direction}"


def _footer(app: DataGridColumnChooserExampleApp) -> str:
    return (
        "Columns: space show/hide, [/ ] width, Ctrl-Up/Down move, s sort | "
        f"tab panes | q quit | {app.status}"
    )


def _style(text: str, token: str) -> str:
    return apply_theme_style(text, COLUMN_CHOOSER_THEME.resolve(token))


def _should_quit(event: InputEvent) -> bool:
    return (
        event.kind == "key"
        and event.key in {"q", "ctrl+c"}
        or event.kind == "text"
        and event.text.lower() == "q"
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
