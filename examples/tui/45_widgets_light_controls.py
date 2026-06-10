from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    Menu,
    MenuItem,
    RenderConstraints,
    RenderLine,
    RenderResult,
    Spinner,
    TabItem,
    Tabs,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class LightControlsApp(FocusableMixin):
    tabs: Tabs = field(default_factory=lambda: Tabs(_tabs()))
    menu: Menu = field(default_factory=lambda: Menu(_menu_items()))
    spinner_frame: int = 0
    message: str = "Ready"

    def __post_init__(self) -> None:
        super().__init__()
        self.tabs.focus()
        self.menu.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [
            RenderLine(truncate_to_width("Light Controls", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            *self.tabs.render(RenderConstraints(width=constraints.width, max_height=1)).lines,
            *Spinner(label="Syncing", frame=self.spinner_frame).render(
                RenderConstraints(width=constraints.width, max_height=1)
            ).lines,
            RenderLine(""),
            *self.menu.render(RenderConstraints(width=constraints.width, max_height=4)).lines,
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        if getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"left", "right"}:
            result = self.tabs.handle_input(event)
            if result is not None:
                self.message = f"View: {self.tabs.value}"
                return True
            return None
        result = self.menu.handle_input(event)
        if result == "refresh":
            self.spinner_frame += 1
            self.message = "Refreshed"
            return True
        if result == "open":
            self.message = f"Opened {self.tabs.value}"
            return True
        return result


def build_app() -> Tui:
    tui = Tui()
    app = LightControlsApp()
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


def _tabs() -> list[TabItem]:
    return [
        TabItem("overview", "Overview"),
        TabItem("logs", "Logs", badge="3"),
        TabItem("settings", "Settings"),
    ]


def _menu_items() -> list[MenuItem]:
    return [
        MenuItem("open", "Open", description="current view"),
        MenuItem("refresh", "Refresh"),
        MenuItem("archive", "Archive", disabled=True),
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
