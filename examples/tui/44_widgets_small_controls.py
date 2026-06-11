from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    Badge,
    FocusableMixin,
    InputEvent,
    KeyValueItem,
    KeyValueList,
    ProgressBar,
    RenderConstraints,
    RenderLine,
    RenderResult,
    StatusPill,
    Toolbar,
    ToolbarAction,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class SmallControlsApp(FocusableMixin):
    progress: int = 42
    message: str = "Ready"
    toolbar: Toolbar = field(default_factory=lambda: Toolbar(_actions()))

    def __post_init__(self) -> None:
        super().__init__()
        self.toolbar.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        details = KeyValueList(
            [
                KeyValueItem("Model", "Kimi"),
                KeyValueItem("Mode", "safe", description="current"),
                KeyValueItem("Queue", "3 pending"),
            ]
        )
        rows = [
            RenderLine(_header(constraints.width)),
            RenderLine(""),
            *ProgressBar(value=self.progress, total=100, label="Indexing", width=12).render(
                RenderConstraints(width=constraints.width, max_height=1)
            ).lines,
            RenderLine(""),
            *details.render(RenderConstraints(width=constraints.width, max_height=4)).lines,
            RenderLine(""),
            *self.toolbar.render(RenderConstraints(width=constraints.width, max_height=1)).lines,
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        result = self.toolbar.handle_input(event)
        if result == "refresh":
            self.progress = min(100, self.progress + 10)
            self.message = "Refreshed"
            return True
        if result == "cancel":
            self.message = "Cancelled"
            return True
        return result


def build_app() -> Tui:
    tui = Tui()
    app = SmallControlsApp()
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


def _header(width: int) -> str:
    constraints = RenderConstraints(width=max(1, width // 4), max_height=1)
    badge = Badge("beta", kind="info").render(constraints).lines[0].text
    status = StatusPill("ready", status="success").render(constraints).lines[0].text
    return truncate_to_width(f"Small Controls  {badge}  {status}", max_width=width, ellipsis="")


def _actions() -> list[ToolbarAction]:
    return [
        ToolbarAction("Refresh", value="refresh"),
        ToolbarAction("Cancel", value="cancel"),
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
