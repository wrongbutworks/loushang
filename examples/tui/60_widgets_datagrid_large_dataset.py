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
    DeltaFormatter,
    FocusableMixin,
    InputEvent,
    NumberFormatter,
    RenderConstraints,
    RenderLine,
    RenderResult,
    TextInput,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    apply_theme_style,
    normalize_key_id,
    strip_control_sequences,
    truncate_to_width,
    visible_width,
)

ROW_COUNT = 2_000
DATA_GRID_THEME = ThemeResolver(
    defaults={
        "example.dataGrid.title": {"bold": True, "color": "cyan"},
        "example.dataGrid.meta": {"color": "bright_black"},
        "example.dataGrid.error": {"color": "red"},
        "widget.dataGrid.header": {"color": "bright_black"},
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
    search_input: TextInput = field(default_factory=lambda: TextInput(theme=DATA_GRID_THEME))
    goto_input: TextInput = field(default_factory=lambda: TextInput(theme=DATA_GRID_THEME))
    focus_region: str = "grid"
    status: str = "Ready"
    page_size: int = 1

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.focus()

    def focus(self) -> None:
        self.focused = True
        self._focus_grid()

    def blur(self) -> None:
        self.focused = False
        self.grid.blur()
        self.search_input.blur()
        self.goto_input.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        height = min(constraints.max_height, constraints.visible_height or constraints.max_height)
        if height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        grid_height = max(1, height - 5)
        self.page_size = max(1, grid_height - 1)
        if self.focus_region == "grid":
            self._sync_goto_value()

        grid_result = self.grid.render(RenderConstraints(width=width, max_height=grid_height))
        rows: list[RenderLine] = [
            RenderLine(_style(truncate_to_width(f"Large DataGrid | {ROW_COUNT:,} rows", max_width=width, ellipsis=""), "example.dataGrid.title")),
            RenderLine(_search_line(self, width)),
            RenderLine(_control_line(self, width)),
            RenderLine(_style("-" * max(1, width), "example.dataGrid.meta")),
        ]
        grid_start = len(rows)
        rows.extend(grid_result.lines[:grid_height])
        while len(rows) < height - 1:
            rows.append(RenderLine(""))
        footer_token = "example.dataGrid.error" if self.status == "Invalid page" else "example.dataGrid.meta"
        rows.append(RenderLine(_style(truncate_to_width(_footer(self), max_width=width, ellipsis=""), footer_token)))

        cursor = None
        if self.focus_region == "search":
            input_result = self.search_input.render(RenderConstraints(width=_search_field_width(width), max_height=1))
            input_column = input_result.cursor.column if input_result.cursor else 0
            cursor = CursorDeclaration(row=1, column=_search_field_start() + input_column)
        elif self.focus_region == "goto":
            input_result = self.goto_input.render(RenderConstraints(width=_goto_field_width(self), max_height=1))
            input_column = input_result.cursor.column if input_result.cursor else 0
            cursor = CursorDeclaration(row=2, column=_goto_field_start(self) + input_column)
        elif grid_result.cursor is not None:
            cursor = CursorDeclaration(row=grid_start + grid_result.cursor.row, column=grid_result.cursor.column)
        return RenderResult.from_lines(rows[:height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        key = normalize_key_id(getattr(event, "key", "")) if getattr(event, "kind", "") == "key" else ""
        if self.focus_region == "search":
            if key in {"enter", "escape", "down"}:
                self._focus_grid()
                self.status = "Ready"
                return True
            if key == "tab":
                self._focus_goto()
                return True
            if key == "shift+tab":
                self._focus_grid()
                return True
            handled = self.search_input.handle_input(event)
            if handled:
                self._apply_search(self.search_input.value)
            return handled

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
                self._focus_search()
                return True
            return self.goto_input.handle_input(event)

        if key == "tab":
            self._focus_search()
            return True
        if key in {"ctrl+g", "ctrl-g", "ctrl_g"}:
            self._focus_goto()
            return True
        if _is_page_forward(key):
            return self._jump_pages(1)
        if _is_page_backward(key):
            return self._jump_pages(-1)

        result = self.grid.handle_input(event)
        if result is not None:
            self.status = _page_status(self)
            return True
        return None

    def _focus_grid(self) -> None:
        self.focus_region = "grid"
        self.search_input.blur()
        self.goto_input.blur()
        if self.focused:
            self.grid.focus()

    def _focus_search(self) -> None:
        self.focus_region = "search"
        self.grid.blur()
        self.goto_input.blur()
        self.search_input.focus()
        self.search_input.set_selection(0, len(self.search_input.value))
        self.status = "Search"

    def _focus_goto(self) -> None:
        self.focus_region = "goto"
        self.grid.blur()
        self.search_input.blur()
        self.goto_input.focus()
        self.goto_input.set_text(str(_current_page(self)))
        self.goto_input.set_selection(0, len(self.goto_input.value))
        self.status = "Enter page"

    def _sync_goto_value(self) -> None:
        value = str(_current_page(self))
        if self.goto_input.value != value:
            self.goto_input.set_text(value)

    def _apply_search(self, value: str) -> None:
        if self.search_input.value != value:
            self.search_input.set_text(value)
        self.grid.set_filter_query(value, columns=("id", "symbol", "sector", "status"))
        self._repair_filtered_page()
        self._sync_goto_value()
        self.status = _page_status(self)

    def _repair_filtered_page(self) -> None:
        if self.grid.active_row_key in self.grid.view_row_keys:
            return
        for row_key in self.grid.view_row_keys:
            if self.grid.activate_row(row_key):
                return

    def _submit_page(self) -> bool:
        raw_value = self.goto_input.value.strip()
        try:
            requested = int(raw_value)
        except ValueError:
            self.status = "Invalid page"
            return True
        self._go_to_page(requested)
        self._focus_grid()
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


def _control_line(app: LargeDataGridExampleApp, width: int) -> str:
    input_width = _goto_field_width(app)
    input_result = app.goto_input.render(RenderConstraints(width=input_width, max_height=1))
    input_text = _pad_visible(input_result.lines[0].text if input_result.lines else "", input_width)
    prefix = "> " if app.focus_region == "goto" else "  "
    suffix = f"] / {_total_pages(app)}    Row {_active_row_number(app)}/{app.grid.filtered_row_count}    {app.status}"
    return truncate_to_width(f"{prefix}Go to page: [{input_text}{suffix}", max_width=width, ellipsis="")


def _search_line(app: LargeDataGridExampleApp, width: int) -> str:
    input_width = _search_field_width(width)
    input_result = app.search_input.render(RenderConstraints(width=input_width, max_height=1))
    input_text = _pad_visible(input_result.lines[0].text if input_result.lines else "", input_width)
    prefix = "> " if app.focus_region == "search" else "  "
    suffix = f"]    Matches {app.grid.filtered_row_count:,}/{ROW_COUNT:,}"
    return truncate_to_width(f"{prefix}Search: [{input_text}{suffix}", max_width=width, ellipsis="")


def _footer(app: LargeDataGridExampleApp) -> str:
    page = _current_page(app)
    total = app.grid.filtered_row_count
    start = 0 if total == 0 else (page - 1) * app.page_size + 1
    end = min(total, page * app.page_size)
    count_text = f"{total:,} filtered from {ROW_COUNT:,}" if app.grid.has_filter else f"{ROW_COUNT:,}"
    return (
        f"Rows {start}-{end} of {count_text} | Page {page}/{_total_pages(app)} | "
        "PgUp/PgDn | Ctrl-B/Ctrl-F | Home/End | Tab filters | Ctrl-G page | q quit"
    )


def _search_field_width(width: int) -> int:
    return max(8, min(24, width - 36))


def _search_field_start() -> int:
    return visible_width("> Search: [")


def _goto_field_width(app: LargeDataGridExampleApp) -> int:
    return max(4, len(str(_total_pages(app))) + 1)


def _goto_field_start(app: LargeDataGridExampleApp) -> int:
    prefix = "> " if app.focus_region == "goto" else "  "
    return visible_width(f"{prefix}Go to page: [")


def _pad_visible(text: str, width: int) -> str:
    return f"{text}{' ' * max(0, width - visible_width(strip_control_sequences(text)))}"


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


def _is_page_forward(key: str) -> bool:
    return key in {"pageDown", "ctrl+f", "ctrl-f"}


def _is_page_backward(key: str) -> bool:
    return key in {"pageUp", "ctrl+b", "ctrl-b"}


def _style(text: str, token: str) -> str:
    return apply_theme_style(text, DATA_GRID_THEME.resolve(token))


def _should_quit(event: InputEvent, app: object | None = None) -> bool:
    if getattr(app, "focus_region", "grid") in {"search", "goto"}:
        return False
    return (
        event.kind == "key"
        and event.key in {"q", "ctrl+c"}
        or event.kind == "text"
        and event.text.lower() == "q"
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
