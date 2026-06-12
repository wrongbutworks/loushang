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
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

LABEL_WIDTH = 14
LIGHT_CONTROLS_THEME = ThemeResolver(
    defaults={
        "widget.tabs.focus": {"bold": True, "color": "cyan"},
        "widget.tabs.selected": {"color": "green"},
        "widget.menu.focus": {"bold": True, "color": "cyan"},
        "widget.menu.disabled": {"dim": True},
        "widget.menu.description": {"color": "bright_black"},
    }
)


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


@dataclass(slots=True)
class LightControlsApp(FocusableMixin):
    tabs: Tabs = field(default_factory=lambda: Tabs(_tabs(), theme=LIGHT_CONTROLS_THEME))
    menu: Menu = field(default_factory=lambda: Menu(_menu_items(), theme=LIGHT_CONTROLS_THEME))
    spinner_frame: int = 0
    message: str = "Ready"
    focus_region: str = "views"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self._sync_region_focus()

    def _sync_region_focus(self) -> None:
        if self.focus_region == "views":
            self.tabs.focus()
            self.menu.blur()
            return
        self.tabs.blur()
        self.menu.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        value_width = max(1, constraints.width - LABEL_WIDTH)
        tab_result = self.tabs.render(RenderConstraints(width=value_width, max_height=1))
        tab_text = tab_result.lines[0].text if tab_result.lines else ""
        activity_result = Spinner(label="Syncing", frame=self.spinner_frame).render(
            RenderConstraints(width=value_width, max_height=1)
        )
        activity_text = activity_result.lines[0].text if activity_result.lines else ""
        menu_lines = self.menu.render(RenderConstraints(width=value_width, max_height=4)).lines
        menu_indent = " " * LABEL_WIDTH
        rows = [
            RenderLine(truncate_to_width("View Switcher", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            _field("Views", tab_text, width=constraints.width),
            _field("Activity", activity_text, width=constraints.width),
            RenderLine(""),
            RenderLine("Actions"),
            *(
                RenderLine(
                    truncate_to_width(
                        f"{menu_indent}{line.text}",
                        max_width=constraints.width,
                        ellipsis="",
                    )
                )
                for line in menu_lines
            ),
            RenderLine(""),
            _field("Status", self.message, width=constraints.width),
            RenderLine(""),
            RenderLine(
                truncate_to_width(
                    "[tab] region  [left/right] view  [up/down] action  [enter] run  [q] quit",
                    max_width=constraints.width,
                    ellipsis="",
                )
            ),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        if getattr(event, "kind", "") == "key" and getattr(event, "key", "") == "tab":
            self.focus_region = "actions" if self.focus_region == "views" else "views"
            self._sync_region_focus()
            return True
        if self.focus_region == "views":
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
        MenuItem("archive", "Archive", description="disabled", disabled=True),
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
