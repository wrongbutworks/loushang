from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from math import ceil
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    DataGrid,
    DataGridColumn,
    DataGridRow,
    DataGridRowView,
    DeltaFormatter,
    FilterApply,
    FilterBar,
    FilterBoundary,
    FilterField,
    FilterFocusChange,
    FocusableMixin,
    InputEvent,
    NumberFormatter,
    PageNavigation,
    PageNavigationError,
    PageNavigator,
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
)

ROW_COUNT = 2_000
DATA_GRID_THEME = ThemeResolver(
    defaults={
        "example.dataGrid.title": {"bold": True, "color": "cyan"},
        "example.dataGrid.meta": {"color": "bright_black"},
        "example.dataGrid.error": {"color": "red"},
        "widget.dataGrid.header": {"color": "bright_black"},
        "widget.dataGrid.sortHeader": {"bold": True, "color": "yellow"},
        "widget.dataGrid.focusSortHeader": {"bold": True, "color": "bright_yellow", "underline": True},
        "widget.dataGrid.row": {"color": "white"},
        "widget.dataGrid.focusRow": {"bold": True, "color": "cyan"},
        "widget.dataGrid.focusCell": {"bold": True, "color": "cyan"},
        "widget.dataGrid.positive": {"color": "green"},
        "widget.dataGrid.negative": {"color": "red"},
        "widget.dataGrid.neutral": {"color": "bright_black"},
    }
)


@dataclass(slots=True)
class LargeDataGridExampleApp(FocusableMixin):
    grid: DataGrid = field(default_factory=lambda: _large_grid(ROW_COUNT))
    filter_bar: FilterBar = field(default_factory=lambda: _large_filter_bar())
    page_navigator: PageNavigator = field(default_factory=lambda: PageNavigator(theme=DATA_GRID_THEME))
    focus_region: str = "grid"
    status: str = "Ready"
    page_size: int = 1
    min_price_value: float | None = None

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.focus()

    def focus(self) -> None:
        self.focused = True
        self._focus_grid()

    def blur(self) -> None:
        self.focused = False
        self.grid.blur()
        self.filter_bar.blur()
        self.page_navigator.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        height = min(constraints.max_height, constraints.visible_height or constraints.max_height)
        if height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        grid_height = max(1, height - 8)
        self.page_size = max(1, grid_height - 1)
        if self.focus_region == "grid":
            self._sync_goto_value()

        grid_result = self.grid.render(RenderConstraints(width=width, max_height=grid_height))
        self.filter_bar.row_details = {0: f"Matches {self.grid.filtered_row_count:,}/{ROW_COUNT:,}"}
        filter_result = self.filter_bar.render(RenderConstraints(width=width, max_height=2))
        self.page_navigator.detail_text = f"Row {_active_row_number(self)}/{self.grid.filtered_row_count}"
        page_result = self.page_navigator.render(RenderConstraints(width=width, max_height=1))
        rows: list[RenderLine] = [
            RenderLine(_style(truncate_to_width(f"Large DataGrid | {ROW_COUNT:,} rows", max_width=width, ellipsis=""), "example.dataGrid.title")),
            filter_result.lines[0] if len(filter_result.lines) > 0 else RenderLine(""),
            filter_result.lines[1] if len(filter_result.lines) > 1 else RenderLine(""),
            page_result.lines[0] if page_result.lines else RenderLine(""),
            RenderLine(_style("-" * max(1, width), "example.dataGrid.meta")),
        ]
        grid_start = len(rows)
        rows.extend(grid_result.lines[:grid_height])
        while len(rows) < height - 3:
            rows.append(RenderLine(""))
        rows.append(RenderLine(_style(truncate_to_width(_footer_summary(self), max_width=width, ellipsis=""), "example.dataGrid.meta")))
        rows.append(RenderLine(_style(truncate_to_width(_footer_status(self), max_width=width, ellipsis=""), _footer_status_token(self))))
        rows.append(RenderLine(_style(truncate_to_width(_footer_help(), max_width=width, ellipsis=""), "example.dataGrid.meta")))

        cursor = None
        if self.focus_region == "filters" and filter_result.cursor is not None:
            cursor = _cursor_if_visible(rows, row=1 + filter_result.cursor.row, column=filter_result.cursor.column)
        elif self.focus_region == "goto" and page_result.cursor is not None:
            cursor = _cursor_if_visible(rows, row=3, column=page_result.cursor.column)
        elif grid_result.cursor is not None:
            cursor = CursorDeclaration(row=grid_start + grid_result.cursor.row, column=grid_result.cursor.column)
        return RenderResult.from_lines(rows[:height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        key = normalize_key_id(getattr(event, "key", "")) if getattr(event, "kind", "") == "key" else ""
        if self.focus_region == "filters":
            if key in {"ctrl+g", "ctrl-g", "ctrl_g"}:
                if not self._apply_filters():
                    return True
                self._focus_goto()
                return True
            if key in {"escape", "down"}:
                if self._apply_filters():
                    self._focus_grid()
                return True
            result = self.filter_bar.handle_input(event)
            if isinstance(result, FilterApply):
                if self._apply_filters():
                    self._focus_grid()
                return True
            if isinstance(result, FilterFocusChange):
                self.status = _filter_status(result.active_key)
                return True
            if isinstance(result, FilterBoundary):
                if self._apply_filters():
                    if result.direction == "forward":
                        self._focus_goto()
                    else:
                        self._focus_grid()
                return True
            if result:
                self.status = "Enter to apply filters"
            return result

        if self.focus_region == "goto":
            if key == "enter":
                return self._submit_page()
            if key in {"escape", "down"}:
                self._focus_grid()
                self.status = "Ready"
                return True
            if key == "tab":
                self._focus_grid()
                return True
            if key == "shift+tab":
                self._focus_filter("min_price")
                return True
            return self.page_navigator.handle_input(event)

        if key == "tab":
            self._focus_filter("search")
            return True
        if key in {"ctrl+g", "ctrl-g", "ctrl_g"}:
            self._focus_goto()
            return True
        if _is_page_forward(key):
            return self._jump_pages(1)
        if _is_page_backward(key):
            return self._jump_pages(-1)
        if key == "s":
            changed = self.grid.cycle_sort()
            if changed:
                self.status = _sort_status(self)
            return changed

        result = self.grid.handle_input(event)
        if result is not None:
            self.status = _page_status(self)
            return True
        return None

    def _focus_grid(self) -> None:
        self.focus_region = "grid"
        self.filter_bar.blur()
        self.page_navigator.blur()
        if self.focused:
            self.grid.focus()

    def _focus_filter(self, region: str) -> None:
        self.focus_region = "filters"
        self.grid.blur()
        self.page_navigator.blur()
        self.filter_bar.focus(region)
        self.status = _filter_status(region)

    def _focus_goto(self) -> None:
        self.focus_region = "goto"
        self.grid.blur()
        self.filter_bar.blur()
        self.page_navigator.set_page(_current_page(self), total_pages=_total_pages(self))
        self.page_navigator.focus()
        self.status = "Enter page"

    def _sync_goto_value(self) -> None:
        self.page_navigator.set_page(_current_page(self), total_pages=_total_pages(self))

    def _apply_search(self, value: str) -> None:
        self._apply_filters(search=value)

    def _apply_filters(
        self,
        *,
        search: str | None = None,
        sector: str | None = None,
        min_price_text: str | None = None,
    ) -> bool:
        values: dict[str, str] = {}
        if search is not None:
            values["search"] = search
        if sector is not None:
            values["sector"] = sector
        if min_price_text is not None:
            values["min_price"] = min_price_text
        self.filter_bar.set_values(values)

        min_price_status = self._update_min_price_value()
        self.grid.set_filter_query(self.filter_bar.values["search"], columns=("id", "symbol", "sector", "status"))
        self.grid.set_filter_predicate(_filter_predicate(self))
        self._repair_filtered_page()
        self._sync_goto_value()
        self.status = min_price_status or _page_status(self)
        return min_price_status is None

    def _update_min_price_value(self) -> str | None:
        raw_value = self.filter_bar.values["min_price"].strip()
        if not raw_value:
            self.min_price_value = None
            return None
        try:
            self.min_price_value = float(raw_value)
        except ValueError:
            return "Error: Min price must be a number; filters unchanged"
        return None

    def _repair_filtered_page(self) -> None:
        if self.grid.active_row_key in self.grid.view_row_keys:
            return
        for row_key in self.grid.view_row_keys:
            if self.grid.activate_row(row_key):
                return

    def _submit_page(self) -> bool:
        result = self.page_navigator.handle_input(InputEvent(kind="key", key="enter"))
        if isinstance(result, PageNavigation):
            self._go_to_page(result.page)
            self._focus_grid()
        elif isinstance(result, PageNavigationError):
            self.status = result.message
        return True

    def _jump_pages(self, delta: int) -> bool:
        page = _current_page(self)
        next_page = max(1, min(_total_pages(self), page + delta))
        if next_page == page:
            self.status = _page_status(self)
            return False
        self._go_to_page(next_page)
        return True

    def _go_to_page(self, page: int) -> None:
        clamped_page = max(1, min(_total_pages(self), page))
        row_index = (clamped_page - 1) * self.page_size
        for row_key in self.grid.view_row_keys[row_index:]:
            if self.grid.activate_row(row_key):
                break
        self.status = f"Page {clamped_page}/{_total_pages(self)}"


def build_app() -> Tui:
    tui = Tui()
    app = LargeDataGridExampleApp()
    tui.add_child(app)
    tui.set_focus(app)
    return tui


async def main() -> int:
    tui = Tui()
    app = LargeDataGridExampleApp()
    tui.add_child(app)
    tui.set_focus(app)

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if _should_quit(event, app):
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


def _large_grid(row_count: int) -> DataGrid:
    return DataGrid(
        _large_columns(),
        tuple(_large_rows(row_count)),
        cursor_mode="row",
        fixed_columns=1,
        theme=DATA_GRID_THEME,
        wrap_rows=False,
    )


def _large_filter_bar() -> FilterBar:
    return FilterBar(
        (
            FilterField("search", "Search", width=16),
            FilterField("sector", "Sector", width=8),
            FilterField("min_price", "Min price", width=8, row=1),
        ),
        theme=DATA_GRID_THEME,
    )


def _large_columns() -> tuple[DataGridColumn, ...]:
    return (
        DataGridColumn("id", "ID", width=6, align="right", formatter=NumberFormatter(precision=0)),
        DataGridColumn("symbol", "Symbol", width=8),
        DataGridColumn("sector", "Sector", width=12),
        DataGridColumn("price", "Price", width=10, align="right", formatter=NumberFormatter(precision=2)),
        DataGridColumn("change", "Change", width=9, align="right", formatter=DeltaFormatter(precision=2), theme_token_for_value=_delta_token),
        DataGridColumn("volume", "Volume", width=11, align="right", formatter=NumberFormatter(precision=0, thousands=True)),
        DataGridColumn("status", "Status", width=10),
    )


def _large_rows(row_count: int) -> tuple[DataGridRow, ...]:
    sectors = ("AI", "Cloud", "Energy", "Fintech", "Health", "Industrial")
    statuses = ("active", "watch", "review", "paused")
    rows: list[DataGridRow] = []
    for index in range(row_count):
        rows.append(
            DataGridRow(
                f"row-{index}",
                {
                    "id": index + 1,
                    "symbol": f"STK{index + 1:04d}",
                    "sector": sectors[index % len(sectors)],
                    "price": round(20.0 + (index % 137) * 1.17 + (index // 137) * 0.05, 2),
                    "change": round(((index % 21) - 10) / 10, 2),
                    "volume": 100_000 + index * 137,
                    "status": statuses[index % len(statuses)],
                },
            )
        )
    return tuple(rows)


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


def _filter_label(region: str) -> str:
    labels = {
        "search": "Search",
        "sector": "Sector",
        "min_price": "Min price",
    }
    return labels[region]


def _footer_summary(app: LargeDataGridExampleApp) -> str:
    page = _current_page(app)
    total = app.grid.filtered_row_count
    start = 0 if total == 0 else (page - 1) * app.page_size + 1
    end = min(total, page * app.page_size)
    count_text = f"{total:,}/{ROW_COUNT:,}" if app.grid.has_filter else f"{ROW_COUNT:,}"
    return f"Rows {start}-{end} of {count_text} | Page {page}/{_total_pages(app)} | {_sort_status(app)}"


def _footer_status(app: LargeDataGridExampleApp) -> str:
    return f"Status: {app.status}"


def _footer_status_token(app: LargeDataGridExampleApp) -> str:
    if app.status == "Invalid page" or app.status.startswith("Error:"):
        return "example.dataGrid.error"
    return "example.dataGrid.meta"


def _footer_help() -> str:
    return "PgUp/PgDn | Ctrl-B/F | Home/End | Tab filters | Ctrl-G page | q quit"


def _cursor_if_visible(lines: list[RenderLine], *, row: int, column: int) -> CursorDeclaration | None:
    if row < 0 or row >= len(lines):
        return None
    if column < 0 or column > lines[row].width:
        return None
    return CursorDeclaration(row=row, column=column)


def _active_row_index(app: LargeDataGridExampleApp) -> int:
    row_key = app.grid.active_row_key
    if row_key is None:
        return 0
    try:
        return app.grid.view_row_keys.index(row_key)
    except ValueError:
        return 0


def _active_row_number(app: LargeDataGridExampleApp) -> int:
    return 0 if app.grid.filtered_row_count == 0 else _active_row_index(app) + 1


def _current_page(app: LargeDataGridExampleApp) -> int:
    return _active_row_index(app) // max(1, app.page_size) + 1


def _total_pages(app: LargeDataGridExampleApp) -> int:
    return max(1, ceil(app.grid.filtered_row_count / max(1, app.page_size)))


def _page_status(app: LargeDataGridExampleApp) -> str:
    return f"Page {_current_page(app)}/{_total_pages(app)}"


def _filter_status(region: str) -> str:
    labels = {
        "search": "Search",
        "sector": "Sector",
        "min_price": "Min price",
    }
    return labels.get(region, "Ready")


def _filter_predicate(app: LargeDataGridExampleApp) -> object:
    sector_value = app.filter_bar.values["sector"].strip().casefold()
    min_price = app.min_price_value
    if not sector_value and min_price is None:
        return None

    def predicate(row: DataGridRowView) -> bool:
        values = row.values
        if sector_value and sector_value not in str(values["sector"]).casefold():
            return False
        if min_price is not None and float(values["price"]) < min_price:
            return False
        return True

    return predicate


def _sort_status(app: LargeDataGridExampleApp) -> str:
    if app.grid.sort_state is None:
        return "Sort none"
    column_key, direction = app.grid.sort_state
    column = _column_by_key(app.grid, column_key)
    label = column.header if column is not None else column_key
    return f"Sort {label} {direction}"


def _column_by_key(grid: DataGrid, key: str) -> DataGridColumn | None:
    for column in grid.columns:
        if column.key == key:
            return column
    return None


def _is_page_forward(key: str) -> bool:
    return key in {"pageDown", "ctrl+f", "ctrl-f"}


def _is_page_backward(key: str) -> bool:
    return key in {"pageUp", "ctrl+b", "ctrl-b"}


def _style(text: str, token: str) -> str:
    return apply_theme_style(text, DATA_GRID_THEME.resolve(token))


def _should_quit(event: InputEvent, app: object | None = None) -> bool:
    if getattr(app, "focus_region", "grid") in {"filters", "goto"}:
        return False
    return (
        event.kind == "key"
        and event.key in {"q", "ctrl+c"}
        or event.kind == "text"
        and event.text.lower() == "q"
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
