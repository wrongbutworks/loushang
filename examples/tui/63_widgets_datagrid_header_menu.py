from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    DataGrid,
    DataGridColumn,
    DeltaFormatter,
    FocusableMixin,
    InputEvent,
    InputIntent,
    Menu,
    MenuItem,
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

GRID_TOP_ROW = 3
MENU_WIDTH = 28

HEADER_MENU_THEME = ThemeResolver(
    defaults={
        "example.dataGrid.title": {"bold": True, "color": "cyan"},
        "example.dataGrid.meta": {"color": "bright_black"},
        "example.dataGrid.status": {"color": "green"},
        "example.overlay.border": {"color": "bright_black"},
        "example.overlay.title": {"bold": True, "color": "cyan"},
        "widget.menu.item": {"color": "white"},
        "widget.menu.focus": {"bold": True, "color": "cyan"},
        "widget.menu.description": {"color": "bright_black"},
        "widget.menu.disabled": {"dim": True},
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
class DataGridHeaderMenuExampleApp(FocusableMixin):
    grid: DataGrid = field(default_factory=lambda: _records_grid())
    status: str = "Move across cells, press m for the active column menu"

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

        grid_height = max(1, height - 5)
        grid_result = self.grid.render(RenderConstraints(width=width, max_height=grid_height))
        rows = [
            RenderLine(_style(truncate_to_width("DataGrid header menu", max_width=width, ellipsis=""), "example.dataGrid.title")),
            RenderLine(_style(truncate_to_width("m menu | arrows move | q quit", max_width=width, ellipsis=""), "example.dataGrid.meta")),
            RenderLine("-" * max(1, width)),
        ]
        rows.extend(grid_result.lines)
        rows.append(RenderLine(""))
        rows.append(RenderLine(_style(truncate_to_width(self.status, max_width=width, ellipsis=""), "example.dataGrid.status")))

        cursor = None
        if grid_result.cursor is not None:
            cursor = CursorDeclaration(row=GRID_TOP_ROW + grid_result.cursor.row, column=grid_result.cursor.column)
        return RenderResult.from_lines(rows[:height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        return self.grid.handle_input(event)


@dataclass(slots=True)
class HeaderMenuOverlay(FocusableMixin):
    app: DataGridHeaderMenuExampleApp
    column_key: str
    menu: Menu = field(init=False)

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.menu = Menu(
            (
                MenuItem("sort_asc", "Sort ascending"),
                MenuItem("sort_desc", "Sort descending"),
                MenuItem("hide", "Hide column"),
            ),
            theme=HEADER_MENU_THEME,
            wrap=False,
        )

    def focus(self) -> None:
        self.focused = True
        self.menu.focus()

    def blur(self) -> None:
        self.focused = False
        self.menu.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = min(MENU_WIDTH, max(12, constraints.width))
        menu_result = self.menu.render(RenderConstraints(width=max(1, width - 4), max_height=3))
        column_label = _column_label(self.app.grid, self.column_key)
        title = _pad_visible(f" Header menu: {column_label} ", max(0, width - 2))

        rows = [
            RenderLine(_style("+" + "-" * max(0, width - 2) + "+", "example.overlay.border")),
            RenderLine(_style("|", "example.overlay.border") + _style(title, "example.overlay.title") + _style("|", "example.overlay.border")),
        ]
        for line in menu_result.lines:
            body = _pad_visible(truncate_to_width(line.text, max_width=max(1, width - 4), ellipsis=""), width - 4)
            rows.append(RenderLine(_style("| ", "example.overlay.border") + body + _style(" |", "example.overlay.border")))
        footer = _pad_visible(" Enter apply | Esc close ", max(0, width - 2))
        rows.append(RenderLine(_style("|", "example.overlay.border") + _style(footer, "example.dataGrid.meta") + _style("|", "example.overlay.border")))
        rows.append(RenderLine(_style("+" + "-" * max(0, width - 2) + "+", "example.overlay.border")))

        return RenderResult.from_lines(rows, constraints=constraints)

    def handle_input(self, event: Any) -> object:
        if getattr(event, "kind", "") == "key" and normalize_key_id(getattr(event, "key", "")) == "escape":
            self.app.status = "Header menu closed"
            return InputIntent(kind="surface_close")
        result = self.menu.handle_input(event)
        if isinstance(result, str):
            return self._apply_action(result)
        return result

    def _apply_action(self, action: str) -> object:
        grid = self.app.grid
        label = _column_label(grid, self.column_key)
        if action == "sort_asc":
            grid.sort_by(self.column_key, "asc")
            self.app.status = f"Sorted {label} asc"
            return InputIntent(kind="surface_close")
        if action == "sort_desc":
            grid.sort_by(self.column_key, "desc")
            self.app.status = f"Sorted {label} desc"
            return InputIntent(kind="surface_close")
        if action == "hide":
            grid.set_column_hidden(self.column_key)
            self.app.status = f"Hid {label}"
            return InputIntent(kind="surface_close")
        return None


def build_app_parts() -> tuple[Tui, DataGridHeaderMenuExampleApp]:
    tui = Tui()
    app = DataGridHeaderMenuExampleApp()
    tui.add_child(app)
    tui.set_focus(app)

    def open_header_menu(event: object) -> object:
        if tui.surface_host.entries:
            return None
        kind = getattr(event, "kind", "")
        key = normalize_key_id(getattr(event, "key", "")) if kind == "key" else ""
        text = getattr(event, "text", "") if kind == "text" else ""
        if (key or text) != "m":
            return None
        column_key = app.grid.active_column_key
        if column_key is None:
            app.status = "No active column"
            return True
        overlay = HeaderMenuOverlay(app, column_key)
        app.status = f"Header menu {_column_label(app.grid, column_key)}"
        tui.show_overlay(
            overlay,
            focus_target=overlay,
            presentation="overlay",
            row=GRID_TOP_ROW,
            column=_header_menu_column(app.grid),
            width=MENU_WIDTH,
            max_height=7,
            margin={"top": 2, "right": 1, "bottom": 2, "left": 1},
        )
        return True

    tui.add_input_listener(open_header_menu)
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
        theme=HEADER_MENU_THEME,
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


def _header_menu_column(grid: DataGrid) -> int:
    offset = 2
    for column in _visible_columns(grid):
        if column.key == grid.active_column_key:
            return offset
        offset += max(0, column.width or column.min_width) + 2
    return 2


def _visible_columns(grid: DataGrid) -> tuple[DataGridColumn, ...]:
    return tuple(column for column in grid.columns if not column.hidden)


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


def _pad_visible(text: str, width: int) -> str:
    return f"{text}{' ' * max(0, width - visible_width(text))}"


def _style(text: str, token: str) -> str:
    return apply_theme_style(text, HEADER_MENU_THEME.resolve(token))


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
