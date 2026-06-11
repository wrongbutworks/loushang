from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    Form,
    FormRow,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    TextArea,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class TextAreaApp(FocusableMixin):
    notes: TextArea = field(default_factory=lambda: TextArea(label="Notes", placeholder="Write notes", height=5))
    message: str = "Enter adds a line. Press q to quit."
    form: Form = field(init=False)

    def __post_init__(self) -> None:
        super().__init__()
        self.form = Form([FormRow("notes", self.notes)])
        self.form.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        body = self.form.render(RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2)))
        rows = [
            *body.lines,
            RenderLine(""),
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=body.cursor)

    def handle_input(self, event: Any) -> object:
        return self.form.handle_input(event)


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
