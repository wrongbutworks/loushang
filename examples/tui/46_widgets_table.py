from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    Table,
    TableColumn,
    TableRow,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class TableApp(FocusableMixin):
    table: Table = field(default_factory=lambda: Table(_columns(), _rows()))
    message: str = "Select a job"

    def __post_init__(self) -> None:
        super().__init__()
        self.table.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [
            RenderLine(truncate_to_width("Table", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            *self.table.render(
                RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 4))
            ).lines,
            RenderLine(""),
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        result = self.table.handle_input(event)
        if isinstance(result, str):
            self.message = f"Selected {result}"
            return True
        return result


def build_app() -> Tui:
    tui = Tui()
    app = TableApp()
    tui.add_child(app)
    tui.set_focus(app)
    return tui


async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if event.kind == "text" and "q" in event.text.lower():
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


def _columns() -> list[TableColumn]:
    return [
        TableColumn("job", "Job", width=12),
        TableColumn("status", "Status"),
        TableColumn("runs", "Runs", width=5, align="right"),
    ]


def _rows() -> list[TableRow]:
    return [
        TableRow("build", {"job": "Build", "status": "ready", "runs": 12}),
        TableRow("deploy", {"job": "Deploy", "status": "blocked", "runs": 3}),
        TableRow(
            "archive",
            {"job": "Archive", "status": "disabled", "runs": 0},
            disabled=True,
        ),
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
