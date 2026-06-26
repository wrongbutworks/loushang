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
    InputIntent,
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

PANEL_WIDTH = 44

COLUMN_CHOOSER_OVERLAY_THEME = ThemeResolver(
    defaults={
        "example.dataGrid.title": {"bold": True, "color": "cyan"},
        "example.dataGrid.meta": {"color": "bright_black"},
        "example.dataGrid.status": {"color": "green"},
        "example.overlay.border": {"color": "bright_black"},
        "example.overlay.title": {"bold": True, "color": "cyan"},
        "widget.columnChooser.row": {"color": "white"},
        "widget.columnChooser.focus": {"bold": True, "color": "cyan"},
        "widget.columnChooser.hidden": {"color": "bright_black"},
        "widget.columnChooser.disabled": {"dim": True},
        "widget.dataGrid.header": {"color": "bright_black"},
        "widget.dataGrid.sortHeader": {"bold": True, "color": "yellow"},
        "widget.dataGrid.focusSortHeader": {"bold": True, "color": "bright_yellow", "underline": True},
        "widget.dataGrid.row": {"color": "white"},
        "widget.dataGrid.focusCell": {"bold": True, "color": "cyan"},
        "widget.dataGrid.fixedColumn": {"color": "bright_white"},
        "widget.dataGrid.positive": {"color": "green"},
        "widget.dataGrid.negative": {"color": "red"},
        "widget.dataGrid.neutral": {"color": "bright_black"},
    }
)


@dataclass(slots=True)
class DataGridColumnChooserOverlayExampleApp(FocusableMixin):
    grid: DataGrid = field(default_factory=lambda: _records_grid())
    status: str = "Press c to customize columns"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.focus()

    def focus(self) -> None:
        self.focused = True
        self.grid.focus()

    def blur(self) -> None:
        self.focused = False
        self.grid.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        height = min(constraints.max_height, constraints.visible_height or constraints.max_height)
        if height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        body_height = max(1, height - 5)
        grid_result = self.grid.render(RenderConstraints(width=width, max_height=body_height))
        rows = [
            RenderLine(_style(truncate_to_width("DataGrid column chooser overlay", max_width=width, ellipsis=""), "example.dataGrid.title")),
            RenderLine(_style(truncate_to_width("c open columns | q quit", max_width=width, ellipsis=""), "example.dataGrid.meta")),
            RenderLine("-" * max(1, width)),
        ]
        rows.extend(grid_result.lines)
        rows.append(RenderLine(""))
        rows.append(RenderLine(_style(truncate_to_width(self.status, max_width=width, ellipsis=""), "example.dataGrid.status")))

        cursor = None
        if grid_result.cursor is not None:
            cursor = CursorDeclaration(row=3 + grid_result.cursor.row, column=grid_result.cursor.column)
        return RenderResult.from_lines(rows[:height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        return self.grid.handle_input(event)


@dataclass(slots=True)
class ColumnChooserOverlay(FocusableMixin):
    app: DataGridColumnChooserOverlayExampleApp
    column_chooser: ColumnChooser = field(init=False)

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.column_chooser = ColumnChooser(
            _column_chooser_columns(self.app.grid),
            theme=COLUMN_CHOOSER_OVERLAY_THEME,
        )

    def focus(self) -> None:
        self.focused = True
        self.column_chooser.focus()

    def blur(self) -> None:
        self.focused = False
        self.column_chooser.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = min(PANEL_WIDTH, max(12, constraints.width))
        chooser_height = max(1, min(len(self.column_chooser.columns), max(1, constraints.max_height - 5)))
        chooser_result = self.column_chooser.render(
            RenderConstraints(width=max(1, width - 4), max_height=chooser_height)
        )

        title = _pad_visible(" Column chooser ", max(0, width - 2))
        rows = [
            RenderLine(_style("+" + "-" * max(0, width - 2) + "+", "example.overlay.border")),
            RenderLine(_style("|", "example.overlay.border") + _style(title, "example.overlay.title") + _style("|", "example.overlay.border")),
        ]
        for line in chooser_result.lines:
            body = _pad_visible(truncate_to_width(line.text, max_width=max(1, width - 4), ellipsis=""), width - 4)
            rows.append(
                RenderLine(
                    _style("| ", "example.overlay.border")
                    + body
                    + _style(" |", "example.overlay.border")
                )
            )
        footer = _pad_visible(" Enter select | Esc close ", max(0, width - 2))
        rows.append(RenderLine(_style("|", "example.overlay.border") + _style(footer, "example.dataGrid.meta") + _style("|", "example.overlay.border")))
        rows.append(RenderLine(_style("+" + "-" * max(0, width - 2) + "+", "example.overlay.border")))

        cursor = None
        if chooser_result.cursor is not None:
            cursor = CursorDeclaration(row=2 + chooser_result.cursor.row, column=2 + chooser_result.cursor.column)
        return RenderResult.from_lines(rows, constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        result = self.column_chooser.handle_input(event)
        return self._handle_column_chooser_result(result)

    def _handle_column_chooser_result(self, result: object) -> object:
        grid = self.app.grid
        if isinstance(result, ColumnChooserToggle):
            grid.toggle_column(result.column_key)
            self._sync_column_chooser(active_key=result.column_key)
            column = _column_by_key(grid, result.column_key)
            state = "hidden" if column is not None and column.hidden else "visible"
            self.app.status = f"{_column_label(grid, result.column_key)} {state}"
            return True
        if isinstance(result, ColumnChooserWidthChange):
            column = _column_by_key(grid, result.column_key)
            if column is None:
                self.app.status = "Missing column"
                return True
            width = column.width if column.width is not None else 8
            grid.set_column_width(result.column_key, max(3, width + result.delta))
            self._sync_column_chooser(active_key=result.column_key)
            next_column = _column_by_key(grid, result.column_key)
            self.app.status = f"{_column_label(grid, result.column_key)} width {next_column.width if next_column else width}"
            return True
        if isinstance(result, ColumnChooserMove):
            moved = self._move_column(result.column_key, result.direction)
            self._sync_column_chooser(active_key=result.column_key)
            self.app.status = f"{_column_label(grid, result.column_key)} moved" if moved else "Column edge"
            return True
        if isinstance(result, ColumnChooserSort):
            changed = grid.cycle_sort(result.column_key)
            self._sync_column_chooser(active_key=result.column_key)
            self.app.status = _sort_status(grid) if changed else "Sort unchanged"
            return True
        if isinstance(result, ColumnChooserSelect):
            row_key = grid.active_row_key
            if row_key is not None:
                grid.activate_cell(row_key, result.column_key)
            self.app.status = f"Selected {_column_label(grid, result.column_key)}"
            return InputIntent(kind="surface_close")
        if isinstance(result, ColumnChooserClose):
            self.app.status = "Column chooser closed"
            return InputIntent(kind="surface_close")
        return result

    def _move_column(self, column_key: str, direction: str) -> bool:
        grid = self.app.grid
        keys = [column.key for column in grid.columns]
        if column_key not in keys:
            return False
        position = keys.index(column_key)
        delta = -1 if direction == "up" else 1
        next_position = max(0, min(len(keys) - 1, position + delta))
        if next_position == position:
            return False
        target = keys[next_position]
        return (
            grid.move_column(column_key, before=target)
            if next_position < position
            else grid.move_column(column_key, after=target)
        )

    def _sync_column_chooser(self, *, active_key: str | None = None) -> None:
        self.column_chooser.set_columns(_column_chooser_columns(self.app.grid), active_key=active_key)


def build_app_parts() -> tuple[Tui, DataGridColumnChooserOverlayExampleApp]:
    tui = Tui()
    app = DataGridColumnChooserOverlayExampleApp()
    tui.add_child(app)
    tui.set_focus(app)

    def open_column_chooser(event: object) -> object:
        if tui.surface_host.entries:
            return None
        kind = getattr(event, "kind", "")
        key = normalize_key_id(getattr(event, "key", "")) if kind == "key" else ""
        text = getattr(event, "text", "") if kind == "text" else ""
        if (key or text) not in {"c", "ctrl+o"}:
            return None
        overlay = ColumnChooserOverlay(app)
        app.status = "Column chooser open"
        tui.show_overlay(
            overlay,
            focus_target=overlay,
            presentation="overlay",
            anchor="top-right",
            width=PANEL_WIDTH,
            max_height=12,
            margin={"top": 2, "right": 2, "bottom": 2, "left": 2},
        )
        return True

    tui.add_input_listener(open_column_chooser)
    return tui, app


def build_app() -> Tui:
    tui, _app = build_app_parts()
    return tui


async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if _should_quit(event, tui):
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
            {"symbol": "TSLA", "price": 181.22, "change": -4.04, "change_pct": -0.0218},
        ),
        columns=_market_columns(),
        row_key_field="symbol",
        cursor_mode="cell",
        fixed_columns=1,
        theme=COLUMN_CHOOSER_OVERLAY_THEME,
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


def _pad_visible(text: str, width: int) -> str:
    return f"{text}{' ' * max(0, width - visible_width(text))}"


def _style(text: str, token: str) -> str:
    return apply_theme_style(text, COLUMN_CHOOSER_OVERLAY_THEME.resolve(token))


def _should_quit(event: InputEvent, tui: Tui) -> bool:
    if tui.surface_host.entries:
        return False
    return (
        event.kind == "key"
        and event.key in {"q", "ctrl+c"}
        or event.kind == "text"
        and event.text.lower() == "q"
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
