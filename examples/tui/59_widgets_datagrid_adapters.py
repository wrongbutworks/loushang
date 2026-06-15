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

LEFT_WIDTH = 22

ADAPTER_THEME = ThemeResolver(
    defaults={
        "example.dataGrid.title": {"bold": True, "color": "cyan"},
        "example.dataGrid.sidebar": {"color": "white"},
        "example.dataGrid.sidebarActive": {"bold": True, "color": "cyan"},
        "example.dataGrid.meta": {"color": "bright_black"},
        "widget.dataGrid.header": {"color": "bright_black"},
        "widget.dataGrid.row": {"color": "white"},
        "widget.dataGrid.focusRow": {"bold": True, "color": "cyan"},
        "widget.dataGrid.focusCell": {"bold": True, "color": "cyan"},
        "widget.dataGrid.disabled": {"dim": True},
        "widget.dataGrid.empty": {"color": "bright_black"},
        "widget.dataGrid.positive": {"color": "green"},
        "widget.dataGrid.negative": {"color": "red"},
        "widget.dataGrid.neutral": {"color": "bright_black"},
    }
)


@dataclass(frozen=True, slots=True)
class AdapterScenario:
    key: str
    title: str
    grid: DataGrid


@dataclass(slots=True)
class DataGridAdapterExampleApp(FocusableMixin):
    scenarios: tuple[AdapterScenario, ...] = field(default_factory=tuple)
    active_index: int = 0
    focus_region: str = "sidebar"
    status: str = "Records adapter"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.scenarios = (
            AdapterScenario("1", "Records", _records_grid()),
            AdapterScenario("2", "JSON", _json_grid()),
            AdapterScenario("3", "CSV", _csv_grid()),
        )
        self.focus()

    @property
    def active_scenario(self) -> AdapterScenario:
        return self.scenarios[self.active_index]

    def focus(self) -> None:
        self.focused = True
        self._sync_grid_focus()

    def blur(self) -> None:
        self.focused = False
        self.active_scenario.grid.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        height = min(constraints.max_height, constraints.visible_height or constraints.max_height)
        if height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        right_width = max(1, width - LEFT_WIDTH - 3)
        body_height = max(1, height - 4)
        grid_result = self.active_scenario.grid.render(RenderConstraints(width=right_width, max_height=body_height))
        left_lines = self._sidebar_lines(body_height)
        rows = [
            RenderLine(_style(truncate_to_width("DataGrid adapter examples", max_width=width, ellipsis=""), "example.dataGrid.title")),
            RenderLine(""),
        ]
        for index in range(body_height):
            left = left_lines[index] if index < len(left_lines) else ""
            right = grid_result.lines[index].text if index < len(grid_result.lines) else ""
            rows.append(RenderLine(_combine(left, right, width=width)))
        rows.append(RenderLine(""))
        rows.append(RenderLine(_style(truncate_to_width(_footer(self), max_width=width, ellipsis=""), "example.dataGrid.meta")))

        cursor = None
        if self.focus_region == "grid" and grid_result.cursor is not None:
            cursor = CursorDeclaration(row=2 + grid_result.cursor.row, column=LEFT_WIDTH + 3 + grid_result.cursor.column)
        elif self.focus_region == "sidebar":
            cursor = CursorDeclaration(row=2 + self.active_index, column=0)
        return RenderResult.from_lines(rows[:height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        key = normalize_key_id(getattr(event, "key", "")) if getattr(event, "kind", "") == "key" else ""
        if getattr(event, "kind", "") == "text" and self._handle_column_control(getattr(event, "text", "")):
            return True
        if key in {"[", "]", ",", "."} and self._handle_column_control(key):
            return True
        if key == "tab":
            self._set_focus_region("sidebar" if self.focus_region == "grid" else "grid")
            return True
        if self.focus_region == "sidebar":
            return self._handle_sidebar_input(event, key)
        if key == "escape":
            self._set_focus_region("sidebar")
            return True
        return self.active_scenario.grid.handle_input(event)

    def _handle_sidebar_input(self, event: Any, key: str) -> object:
        if key == "up":
            return self._move_sidebar(-1)
        if key == "down":
            return self._move_sidebar(1)
        if key in {"enter", "right"}:
            self._set_focus_region("grid")
            return True
        if getattr(event, "kind", "") == "text":
            text = getattr(event, "text", "")
            if text in {scenario.key for scenario in self.scenarios}:
                self._select_scenario(text)
                return True
        return None

    def _move_sidebar(self, delta: int) -> bool:
        next_index = max(0, min(len(self.scenarios) - 1, self.active_index + delta))
        if next_index == self.active_index:
            return False
        self.active_scenario.grid.blur()
        self.active_index = next_index
        self._sync_grid_focus()
        self.status = f"{self.active_scenario.title} adapter"
        return True

    def _select_scenario(self, key: str) -> None:
        for index, scenario in enumerate(self.scenarios):
            if scenario.key == key:
                self.active_scenario.grid.blur()
                self.active_index = index
                self._sync_grid_focus()
                self.status = f"{scenario.title} adapter"
                return

    def _set_focus_region(self, region: str) -> None:
        if region == self.focus_region:
            return
        self.focus_region = region
        self._sync_grid_focus()
        self.status = "Adapter list" if region == "sidebar" else self.active_scenario.title

    def _sync_grid_focus(self) -> None:
        if self.focused and self.focus_region == "grid":
            self.active_scenario.grid.focus()
        else:
            self.active_scenario.grid.blur()

    def _handle_column_control(self, action: str) -> bool:
        if action == "v":
            return self._toggle_change_percent_column()
        if action == "[":
            return self._adjust_price_width(-1)
        if action == "]":
            return self._adjust_price_width(1)
        if action == ",":
            return self._move_price_column(-1)
        if action == ".":
            return self._move_price_column(1)
        return False

    def _toggle_change_percent_column(self) -> bool:
        grid = self.active_scenario.grid
        column = _column_by_key(grid, "change_pct")
        if column is None:
            self.status = "No Change % column"
            return True
        grid.toggle_column("change_pct")
        next_column = _column_by_key(grid, "change_pct")
        state = "hidden" if next_column is not None and next_column.hidden else "visible"
        self.status = f"Change % {state}"
        return True

    def _adjust_price_width(self, delta: int) -> bool:
        grid = self.active_scenario.grid
        column = _column_by_key(grid, "price")
        if column is None:
            self.status = "No Price column"
            return True
        width = column.width if column.width is not None else 9
        grid.set_column_width("price", max(3, width + delta))
        next_column = _column_by_key(grid, "price")
        self.status = f"Price width {next_column.width if next_column is not None else width}"
        return True

    def _move_price_column(self, delta: int) -> bool:
        grid = self.active_scenario.grid
        visible = [column.key for column in grid.columns if not column.hidden]
        if "price" not in visible:
            self.status = "No visible Price column"
            return True
        position = visible.index("price")
        next_position = max(0, min(len(visible) - 1, position + delta))
        if next_position == position:
            self.status = "Price column edge"
            return True
        target = visible[next_position]
        moved = (
            grid.move_column("price", before=target)
            if next_position < position
            else grid.move_column("price", after=target)
        )
        self.status = "Price column moved" if moved else "Price column unchanged"
        return True

    def _sidebar_lines(self, height: int) -> list[str]:
        lines: list[str] = []
        for index, scenario in enumerate(self.scenarios):
            if index == self.active_index:
                prefix = "> " if self.focus_region == "sidebar" else "* "
            else:
                prefix = "  "
            text = truncate_to_width(f"{prefix}{scenario.key} {scenario.title}", max_width=LEFT_WIDTH, ellipsis="")
            token = "example.dataGrid.sidebarActive" if index == self.active_index else "example.dataGrid.sidebar"
            lines.append(_style(text, token))
        while len(lines) < height:
            lines.append("")
        return lines


def build_app() -> Tui:
    tui = Tui()
    app = DataGridAdapterExampleApp()
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
        theme=ADAPTER_THEME,
        wrap_rows=False,
    )


def _json_grid() -> DataGrid:
    return DataGrid.from_json(
        {
            "records": [
                {"job": "Build", "status": "ready", "runs": 12},
                {"job": "Deploy", "status": "blocked", "runs": 3},
                {"job": "Archive", "status": "disabled", "runs": 0},
            ]
        },
        columns=(
            DataGridColumn("job", "Job", width=12),
            DataGridColumn("status", "Status", width=12),
            DataGridColumn("runs", "Runs", width=6, align="right"),
        ),
        row_key_field="job",
        cursor_mode="row",
        theme=ADAPTER_THEME,
        wrap_rows=False,
    )


def _csv_grid() -> DataGrid:
    return DataGrid.from_csv(
        "symbol,price,change,change_pct\n"
        "AAPL,213.41,2.18,0.0103\n"
        "MSFT,491.72,-1.64,-0.0033\n"
        "NVDA,142.83,0.0,0.0\n",
        columns=_market_columns(),
        row_key_field="symbol",
        cursor_mode="cell",
        fixed_columns=1,
        theme=ADAPTER_THEME,
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


def _style(text: str, token: str) -> str:
    return apply_theme_style(text, ADAPTER_THEME.resolve(token))


def _column_by_key(grid: DataGrid, key: str) -> DataGridColumn | None:
    for column in grid.columns:
        if column.key == key:
            return column
    return None


def _footer(app: DataGridAdapterExampleApp) -> str:
    return truncate_to_width(
        f"{app.active_scenario.title} | v hide %, [/ ] width, ,/. move | tab panes | q quit | {app.status}",
        max_width=120,
        ellipsis="",
    )


def _should_quit(event: InputEvent) -> bool:
    return (
        event.kind == "key"
        and event.key in {"q", "ctrl+c"}
        or event.kind == "text"
        and event.text.lower() == "q"
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
