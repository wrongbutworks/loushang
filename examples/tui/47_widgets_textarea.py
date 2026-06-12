from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    TextArea,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

LABEL_WIDTH = 14
TEXTAREA_EXAMPLE_THEME = ThemeResolver(
    defaults={
        "widget.textArea.placeholder": {"color": "bright_black"},
        "widget.textArea.text": {"color": "white"},
    }
)


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


def _line_count(value: str) -> int:
    if not value:
        return 0
    return value.count("\n") + 1


def _line_count_label(count: int) -> str:
    return f"{count} line / unsaved" if count == 1 else f"{count} lines / unsaved"


@dataclass(slots=True)
class TextAreaApp(FocusableMixin):
    notes: TextArea = field(
        default_factory=lambda: TextArea(placeholder="Write notes", height=5, theme=TEXTAREA_EXAMPLE_THEME)
    )
    message: str = ""

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.notes.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        body = self.notes.render(RenderConstraints(width=constraints.width, max_height=5))
        status = _line_count_label(_line_count(self.notes.value))
        prefix = [
            RenderLine(truncate_to_width("Release Note Draft", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            _field("Title", "Weekly deploy notes", width=constraints.width),
            RenderLine(""),
            RenderLine("Notes"),
        ]
        rows = [
            *prefix,
            *body.lines,
            _field("Status", status, width=constraints.width),
            RenderLine(""),
            RenderLine(
                truncate_to_width(
                    "[enter] newline  [type] edit  [q] quit",
                    max_width=constraints.width,
                    ellipsis="",
                )
            ),
        ]
        cursor = None
        if body.cursor is not None:
            cursor = CursorDeclaration(row=body.cursor.row + len(prefix), column=body.cursor.column)
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        return self.notes.handle_input(event)


def build_app() -> Tui:
    tui = Tui()
    app = TextAreaApp()
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


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
