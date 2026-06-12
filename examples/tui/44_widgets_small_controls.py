from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    Badge,
    FocusableMixin,
    InputEvent,
    ProgressBar,
    RenderConstraints,
    RenderLine,
    RenderResult,
    StatusPill,
    ThemeResolver,
    Toolbar,
    ToolbarAction,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

LABEL_WIDTH = 14
SMALL_CONTROLS_THEME = ThemeResolver(
    defaults={
        "widget.toolbar.action": {"color": "white"},
        "widget.toolbar.focus": {"bold": True, "color": "cyan"},
        "widget.toolbar.disabled": {"dim": True},
    }
)


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


@dataclass(slots=True)
class SmallControlsApp(FocusableMixin):
    progress: int = 42
    message: str = "Ready"
    toolbar: Toolbar = field(default_factory=lambda: Toolbar(_actions(), theme=SMALL_CONTROLS_THEME))

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.toolbar.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        value_width = max(1, constraints.width - LABEL_WIDTH)
        progress_result = ProgressBar(value=self.progress, total=100, label="Indexing", width=12).render(
            RenderConstraints(width=value_width, max_height=1)
        )
        progress_text = progress_result.lines[0].text if progress_result.lines else ""
        toolbar_result = self.toolbar.render(
            RenderConstraints(width=value_width, max_height=1)
        )
        toolbar_text = toolbar_result.lines[0].text if toolbar_result.lines else ""
        rows = [
            RenderLine(_header(constraints.width)),
            RenderLine(""),
            _field("Progress", progress_text, width=constraints.width),
            RenderLine(""),
            RenderLine("Details"),
            _field("Model", "Kimi", width=constraints.width),
            _field("Mode", "safe  current", width=constraints.width),
            _field("Queue", "3 pending", width=constraints.width),
            RenderLine(""),
            _field("Actions", toolbar_text, width=constraints.width),
            _field("Status", self.message, width=constraints.width),
            RenderLine(""),
            RenderLine(
                truncate_to_width(
                    "[left/right] action  [enter] run  [q] quit",
                    max_width=constraints.width,
                    ellipsis="",
                )
            ),
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
    return truncate_to_width(f"Indexing Job  {badge}  {status}", max_width=width, ellipsis="")


def _actions() -> list[ToolbarAction]:
    return [
        ToolbarAction("Refresh", value="refresh"),
        ToolbarAction("Cancel", value="cancel"),
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
