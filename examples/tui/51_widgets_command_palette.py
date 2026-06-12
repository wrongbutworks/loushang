from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    CommandPaletteItem,
    CommandPaletteView,
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

LABEL_WIDTH = 14
COMMAND_PALETTE_THEME = ThemeResolver(
    defaults={
        "widget.commandPalette.title": {"bold": True},
        "widget.commandPalette.queryLabel": {"color": "cyan"},
        "widget.commandPalette.queryText": {"color": "white"},
        "widget.commandPalette.placeholder": {"color": "bright_black"},
        "widget.commandPalette.section": {"bold": True},
        "widget.commandPalette.item": {"color": "white"},
        "widget.commandPalette.focus": {"bold": True, "color": "cyan"},
        "widget.commandPalette.disabled": {"dim": True},
        "widget.commandPalette.description": {"color": "bright_black"},
        "widget.commandPalette.empty": {"color": "bright_black"},
        "widget.commandPalette.footer": {"color": "bright_black"},
    }
)


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


@dataclass(slots=True)
class OperationsConsoleApp(FocusableMixin):
    palette: CommandPaletteView = field(
        default_factory=lambda: CommandPaletteView(
            _command_items(),
            close_on_select=False,
            close_on_cancel=False,
            theme=COMMAND_PALETTE_THEME,
        )
    )
    status: str = "Ready"
    last_command: str = "none"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.focus()

    def focus(self) -> None:
        self.focused = True
        self.palette.focus()

    def blur(self) -> None:
        self.focused = False
        self.palette.blur()

    def editor_input_target(self) -> object | None:
        return self.palette.editor_input_target()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        palette_result = self.palette.render(
            RenderConstraints(
                width=constraints.width,
                max_height=max(1, constraints.max_height - 8),
            )
        )
        rows = [
            RenderLine(truncate_to_width("Operations Console", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            _field("Status", self.status, width=constraints.width),
            RenderLine(""),
            RenderLine("Commands"),
            *palette_result.lines,
            RenderLine(""),
            RenderLine(
                truncate_to_width(
                    "[up/down] command  [enter] run  [esc] cancel  [q] quit",
                    max_width=constraints.width,
                    ellipsis="",
                )
            ),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        result = self.palette.handle_input(event)
        for intent in _as_intents(result):
            kind = getattr(intent, "kind", "")
            if kind == "command_select":
                self.last_command = str(getattr(intent, "text", ""))
                label = str(getattr(intent, "note", "")) or self.last_command
                self.status = f"Selected: {label}"
                return True
            if kind == "command_cancel":
                self.status = "Cancelled"
                return True
        return result


def build_app() -> Tui:
    tui = Tui()
    app = OperationsConsoleApp()
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


def _command_items() -> tuple[CommandPaletteItem, ...]:
    return (
        CommandPaletteItem("deploy", "Deploy service", "Run deployment pipeline"),
        CommandPaletteItem("logs", "Open logs", "Show latest logs"),
        CommandPaletteItem("tests", "Run tests", "Execute test suite"),
        CommandPaletteItem("cache", "Clear cache", "Invalidate local cache"),
        CommandPaletteItem("worker", "Restart worker", "Restart background worker"),
        CommandPaletteItem("archive", "Archive release", "unavailable", disabled=True),
    )


def _as_intents(result: object) -> tuple[object, ...]:
    if isinstance(result, tuple):
        return result
    return (result,) if result is not None and result is not True else ()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
