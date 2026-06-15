from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    CompactNumberFormatter,
    CursorDeclaration,
    DataGrid,
    DataGridColumn,
    DataGridEdit,
    DataGridRow,
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
    truncate_to_width,
    visible_width,
)

LEFT_WIDTH = 24

DATAGRID_THEME = ThemeResolver(
    defaults={
        "example.dataGrid.title": {"bold": True, "color": "cyan"},
        "example.dataGrid.sidebar": {"color": "white"},
        "example.dataGrid.sidebarActive": {"bold": True, "color": "cyan"},
        "example.dataGrid.meta": {"color": "bright_black"},
        "example.dataGrid.status": {"color": "green"},
        "widget.dataGrid.header": {"color": "bright_black"},
        "widget.dataGrid.row": {"color": "white"},
        "widget.dataGrid.focusRow": {"bold": True, "color": "cyan"},
        "widget.dataGrid.focusCell": {"bold": True, "color": "cyan"},
        "widget.dataGrid.focusColumn": {"bold": True, "color": "cyan"},
        "widget.dataGrid.disabled": {"dim": True},
        "widget.dataGrid.empty": {"color": "bright_black"},
        "widget.dataGrid.editing": {"bold": True, "color": "yellow"},
        "widget.dataGrid.positive": {"color": "green"},
        "widget.dataGrid.negative": {"color": "red"},
        "widget.dataGrid.neutral": {"color": "bright_black"},
        "widget.dataGrid.warning": {"color": "yellow"},
        "widget.dataGrid.error": {"color": "red"},
    }
)


@dataclass(frozen=True, slots=True)
class Scenario:
    key: str
    title: str
    grid: DataGrid


@dataclass(slots=True)
class DataGridExampleApp(FocusableMixin):
    scenarios: tuple[Scenario, ...] = field(default_factory=tuple)
    active_index: int = 0
    status: str = "Ready"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.scenarios = (
            Scenario("1", "Market watchlist", _watchlist_grid()),
            Scenario("2", "Order entry", _order_grid()),
            Scenario("3", "Job status", _jobs_grid()),
            Scenario("4", "Token usage", _usage_grid()),
            Scenario("5", "Diagnostics", _diagnostics_grid()),
        )
        self.focus()

    @property
    def active_scenario(self) -> Scenario:
        return self.scenarios[self.active_index]

    def focus(self) -> None:
        self.focused = True
        self.active_scenario.grid.focus()

    def blur(self) -> None:
        self.focused = False
        self.active_scenario.grid.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        height = min(constraints.max_height, constraints.visible_height or constraints.max_height)
        if height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        right_width = max(1, width - LEFT_WIDTH - 3)
        grid_height = max(1, height - 4)
        grid_result = self.active_scenario.grid.render(RenderConstraints(width=right_width, max_height=grid_height))
        left_lines = self._sidebar_lines(grid_height)
        rows = [
            RenderLine(_style(truncate_to_width("DataGrid examples", max_width=width, ellipsis=""), "example.dataGrid.title")),
            RenderLine(""),
        ]
        for index in range(grid_height):
            left = left_lines[index] if index < len(left_lines) else ""
            right = grid_result.lines[index].text if index < len(grid_result.lines) else ""
            rows.append(RenderLine(_combine(left, right, width=width)))
        rows.append(RenderLine(""))
        rows.append(RenderLine(_style(truncate_to_width(_footer(self), max_width=width, ellipsis=""), "example.dataGrid.meta")))
        cursor = None
        if grid_result.cursor is not None:
            cursor = CursorDeclaration(row=2 + grid_result.cursor.row, column=LEFT_WIDTH + 3 + grid_result.cursor.column)
        return RenderResult.from_lines(rows[:height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        if getattr(event, "kind", "") == "text":
            text = getattr(event, "text", "")
            if text in {scenario.key for scenario in self.scenarios}:
                self._select_scenario(text)
                return True
        result = self.active_scenario.grid.handle_input(event)
        if isinstance(result, DataGridEdit):
            self.status = f"Edited {result.row_key}.{result.column_key}"
            if self.active_scenario.key == "2":
                _refresh_order_total(self.active_scenario.grid)
            return True
        if result is not None:
            self.status = str(result)
            return True
        return None

    def _select_scenario(self, key: str) -> None:
        for index, scenario in enumerate(self.scenarios):
            if scenario.key == key:
                self.active_scenario.grid.blur()
                self.active_index = index
                self.active_scenario.grid.focus()
                self.status = scenario.title
                return

    def _sidebar_lines(self, height: int) -> list[str]:
        lines: list[str] = []
        for index, scenario in enumerate(self.scenarios):
            prefix = "> " if index == self.active_index else "  "
            text = truncate_to_width(f"{prefix}{scenario.key} {scenario.title}", max_width=LEFT_WIDTH, ellipsis="")
            token = "example.dataGrid.sidebarActive" if index == self.active_index else "example.dataGrid.sidebar"
            lines.append(_style(text, token))
        while len(lines) < height:
            lines.append("")
        return lines


def build_app() -> Tui:
    tui = Tui()
    app = DataGridExampleApp()
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


def _watchlist_grid() -> DataGrid:
    return DataGrid(
        (
            DataGridColumn("symbol", "Symbol", width=7),
            DataGridColumn("price", "Price", width=9, align="right", formatter=NumberFormatter(precision=2, thousands=True)),
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
            DataGridColumn("volume", "Volume", width=8, align="right", formatter=CompactNumberFormatter(precision=1)),
        ),
        (
            DataGridRow("aapl", {"symbol": "AAPL", "price": 213.41, "change": 2.18, "change_pct": 0.0103, "volume": 68300000}),
            DataGridRow("msft", {"symbol": "MSFT", "price": 491.72, "change": -1.64, "change_pct": -0.0033, "volume": 22100000}),
            DataGridRow("nvda", {"symbol": "NVDA", "price": 142.83, "change": 0.0, "change_pct": 0.0, "volume": 174500000}),
        ),
        cursor_mode="cell",
        fixed_columns=1,
        theme=DATAGRID_THEME,
        wrap_rows=False,
    )


def _order_grid() -> DataGrid:
    rows = (
        DataGridRow("line-1", {"code": "A100", "name": "Adapter", "qty": 2, "price": 19.5, "total": 39.0}),
        DataGridRow("line-2", {"code": "B200", "name": "Bracket", "qty": 1, "price": 42.0, "total": 42.0}),
        DataGridRow("total", {"code": "", "name": "Total", "qty": "", "price": "", "total": 81.0}, pinned="bottom"),
    )
    grid = DataGrid(
        (
            DataGridColumn("code", "Code", width=8, editable=True, enter_behavior="edit", edit_next_column_key="qty"),
            DataGridColumn("name", "Name", width=12),
            DataGridColumn("qty", "Qty", width=5, align="right", editable=True, parser=int),
            DataGridColumn("price", "Price", width=8, align="right", formatter=NumberFormatter(precision=2)),
            DataGridColumn("total", "Total", width=9, align="right", formatter=NumberFormatter(precision=2)),
        ),
        rows,
        cursor_mode="cell",
        theme=DATAGRID_THEME,
        wrap_rows=False,
    )
    return grid


def _jobs_grid() -> DataGrid:
    return DataGrid(
        (
            DataGridColumn("job", "Job", width=12),
            DataGridColumn("status", "Status", width=12),
            DataGridColumn("runs", "Runs", width=5, align="right"),
        ),
        (
            DataGridRow("build", {"job": "Build", "status": "ready", "runs": 12}),
            DataGridRow("deploy", {"job": "Deploy", "status": "blocked", "runs": 3}),
            DataGridRow("archive", {"job": "Archive", "status": "disabled", "runs": 0}, disabled=True),
            DataGridRow("release", {"job": "Release", "status": "ready", "runs": 7}),
        ),
        theme=DATAGRID_THEME,
        wrap_rows=False,
    )


def _usage_grid() -> DataGrid:
    return DataGrid(
        (
            DataGridColumn("model", "Model", width=18),
            DataGridColumn("share", "Share", width=8, align="right", formatter=PercentFormatter(precision=1)),
            DataGridColumn("input", "Input", width=9, align="right", formatter=CompactNumberFormatter(precision=1)),
            DataGridColumn("output", "Output", width=9, align="right", formatter=CompactNumberFormatter(precision=1)),
        ),
        (
            DataGridRow("k2", {"model": "kimi-k2.5", "share": 0.827, "input": 146900000, "output": 655000}),
            DataGridRow("coding", {"model": "kimi-for-coding", "share": 0.172, "input": 30100000, "output": 671900}),
            DataGridRow("haiku", {"model": "Haiku 4.5", "share": 0.001, "input": 162800, "output": 1500}),
        ),
        cursor_mode="column",
        theme=DATAGRID_THEME,
    )


def _diagnostics_grid() -> DataGrid:
    return DataGrid(
        (
            DataGridColumn("check", "Check", width=16),
            DataGridColumn("state", "State", width=10, theme_token_for_value=_diagnostic_token),
            DataGridColumn("message", "Message"),
        ),
        (
            DataGridRow("lint", {"check": "Ruff", "state": "ok", "message": "clean"}),
            DataGridRow("tests", {"check": "Pytest", "state": "warning", "message": "slow shard"}),
            DataGridRow("network", {"check": "Network", "state": "error", "message": "offline"}),
        ),
        cursor_mode="cell",
        theme=DATAGRID_THEME,
        wrap_rows=False,
    )


def _refresh_order_total(grid: DataGrid) -> None:
    total = 0.0
    for row_key in grid.row_keys:
        if row_key == "total":
            continue
        qty = grid.cell_value(row_key, "qty") or 0
        price = grid.cell_value(row_key, "price") or 0
        try:
            line_total = float(qty) * float(price)
        except (TypeError, ValueError):
            line_total = 0.0
        grid.update_cell(row_key, "total", line_total)
        total += line_total
    grid.update_cell("total", "total", total)


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


def _diagnostic_token(value: object) -> str | None:
    if value == "warning":
        return "widget.dataGrid.warning"
    if value == "error":
        return "widget.dataGrid.error"
    return "widget.dataGrid.positive" if value == "ok" else None


def _combine(left: str, right: str, *, width: int) -> str:
    left_text = truncate_to_width(left, max_width=LEFT_WIDTH, ellipsis="")
    padding = " " * max(0, LEFT_WIDTH - visible_width(left_text))
    return truncate_to_width(f"{left_text}{padding} | {right}", max_width=width, ellipsis="")


def _style(text: str, token: str) -> str:
    return apply_theme_style(text, DATAGRID_THEME.resolve(token))


def _footer(app: DataGridExampleApp) -> str:
    return truncate_to_width(
        f"{app.active_scenario.title} | 1-5 scenarios | arrows move | e edit | enter activate/commit | space select | q quit | {app.status}",
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
