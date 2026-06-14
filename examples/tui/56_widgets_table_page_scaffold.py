from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    FocusableMixin,
    InputEvent,
    PageScaffold,
    PageScaffoldContext,
    RenderConstraints,
    RenderLine,
    RenderResult,
    TabItem,
    Table,
    TableColumn,
    TableRow,
    Tabs,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

LABEL_WIDTH = 14

TABLE_PAGE_THEME = ThemeResolver(
    defaults={
        "widget.tabs.tab": {"color": "white"},
        "widget.tabs.selected": {"bold": True, "color": "green"},
        "widget.tabs.focus": {"bold": True, "color": "cyan"},
        "widget.tabs.level0.selected_header_focus": {"bold": True, "color": "cyan"},
        "widget.tabs.level0.selected_content_focus": {"bold": True, "color": "green"},
        "widget.pageScaffold.separator": {"color": "bright_black"},
        "widget.pageScaffold.footer": {"color": "bright_black"},
        "widget.table.header": {"color": "bright_black"},
        "widget.table.row": {"color": "white"},
        "widget.table.focus": {"bold": True, "color": "cyan"},
        "widget.table.disabled": {"dim": True},
        "widget.table.empty": {"color": "bright_black"},
    }
)


@dataclass(slots=True)
class TablePage(FocusableMixin):
    title: str
    table: Table
    details: dict[str, str]
    first_value: str
    selected_value: str = ""

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)

    def focus(self) -> None:
        self.focused = True
        self.table.focus()

    def blur(self) -> None:
        self.focused = False
        self.table.blur()

    def handle_input(self, event: Any) -> object:
        key = getattr(event, "key", "") if getattr(event, "kind", "") == "key" else ""
        if key == "up" and self.table.active_value == self.first_value:
            return None
        result = self.table.handle_input(event)
        if isinstance(result, str):
            self.selected_value = result
            return f"Selected: {self.details.get(result, result)}"
        return result

    def render(self, constraints: RenderConstraints) -> RenderResult:
        table_height = max(1, constraints.max_height - 5)
        table_result = self.table.render(RenderConstraints(width=constraints.width, max_height=table_height))
        active_value = self.table.active_value
        detail = self.details.get(self.selected_value or active_value, "Select a row")
        rows = [
            RenderLine(truncate_to_width(self.title, max_width=constraints.width, ellipsis="")),
            *table_result.lines,
            RenderLine(""),
            RenderLine("Details"),
            _field("Selected", detail, width=constraints.width),
        ]
        cursor = None
        if table_result.cursor is not None:
            cursor = CursorDeclaration(row=1 + table_result.cursor.row, column=table_result.cursor.column)
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)


@dataclass(slots=True)
class TableScaffoldDemo(FocusableMixin):
    tabs: Tabs = field(init=False)
    pages: dict[str, TablePage] = field(init=False)
    scaffold: PageScaffold = field(init=False)
    status: str = "Ready"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.tabs = Tabs(
            (
                TabItem("jobs", "Jobs"),
                TabItem("runs", "Runs"),
            ),
            on_change=self._select_tab,
            theme=TABLE_PAGE_THEME,
        )
        self.pages = {
            "jobs": TablePage("Job table", _jobs_table(), _job_details(), first_value="build"),
            "runs": TablePage("Run table", _runs_table(), _run_details(), first_value="plan"),
        }
        self.scaffold = PageScaffold(
            header=self.tabs,
            body=self.pages[self.tabs.value],
            footer=self._footer,
            theme=TABLE_PAGE_THEME,
            focused=True,
            focus_region="body",
            separator_after_header=True,
            body_padding_top=1,
            body_padding_bottom=1,
        )
        self.focus()

    def focus(self) -> None:
        self.focused = True
        self.scaffold.focus()

    def blur(self) -> None:
        self.focused = False
        self.scaffold.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        self.tabs.selected_focus = "header" if self.scaffold.focus_region == "header" else "content"
        return self.scaffold.render(constraints)

    def handle_input(self, event: Any) -> object:
        result = self.scaffold.handle_input(event)
        if isinstance(result, str):
            self.status = result
            return True
        return True if result is not None else None

    def _select_tab(self, value: str) -> bool:
        self.scaffold.body = self.pages[value]
        self.scaffold.focus_region = "header"
        self.status = f"Selected: {value.title()}"
        return True

    def _footer(self, context: PageScaffoldContext) -> str:
        if context.focus_region == "header":
            return f"Tabs | {self.status} | Left/Right switch | Down table | q quit"
        return f"Table | {self.status} | Up/Down row | Enter select | Up tabs | q quit"


def build_app() -> Tui:
    tui = Tui()
    app = TableScaffoldDemo()
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


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


def _jobs_table() -> Table:
    return Table(
        (
            TableColumn("job", "Job", width=12),
            TableColumn("status", "Status"),
            TableColumn("runs", "Runs", width=5, align="right"),
        ),
        (
            TableRow("build", {"job": "Build", "status": "ready", "runs": 12}),
            TableRow("deploy", {"job": "Deploy", "status": "blocked", "runs": 3}),
            TableRow("archive", {"job": "Archive", "status": "disabled", "runs": 0}, disabled=True),
        ),
        theme=TABLE_PAGE_THEME,
        wrap=False,
    )


def _runs_table() -> Table:
    return Table(
        (
            TableColumn("run", "Run", width=12),
            TableColumn("duration", "Duration", width=10, align="right"),
            TableColumn("result", "Result"),
        ),
        (
            TableRow("plan", {"run": "plan", "duration": "00:08", "result": "queued"}),
            TableRow("deploy", {"run": "deploy", "duration": "01:42", "result": "completed"}),
            TableRow("verify", {"run": "verify", "duration": "00:31", "result": "passed"}),
        ),
        theme=TABLE_PAGE_THEME,
        wrap=False,
    )


def _job_details() -> dict[str, str]:
    return {
        "build": "Build is ready, 12 runs",
        "deploy": "Deploy is blocked, 3 runs",
        "archive": "Archive is disabled, 0 runs",
    }


def _run_details() -> dict[str, str]:
    return {
        "plan": "plan queued",
        "deploy": "deploy completed",
        "verify": "verify passed",
    }


def _should_quit(event: InputEvent) -> bool:
    if event.kind == "text" and "q" in event.text.casefold():
        return True
    if event.kind == "key" and event.key in {"q", "ctrl+c"}:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
