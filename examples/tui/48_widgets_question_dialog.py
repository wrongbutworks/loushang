from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    QuestionDialog,
    RenderConstraints,
    RenderLine,
    RenderResult,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class QuestionDialogApp(FocusableMixin):
    dialog: QuestionDialog = field(
        default_factory=lambda: QuestionDialog(
            title="Add note",
            question="What should be remembered?",
            placeholder="Write a multi-line answer",
            help_text="Enter adds a line. Ctrl+Enter submits.",
            required=True,
        )
    )
    message: str = "Escape cancels. Press q to quit."

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.dialog.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        body = self.dialog.render(RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2)))
        rows = [
            *body.lines,
            RenderLine(""),
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=body.cursor)

    def handle_input(self, event: Any) -> object:
        result = self.dialog.handle_input(event)
        intents = result if isinstance(result, tuple) else (() if result is None else (result,))
        for intent in intents:
            if getattr(intent, "kind", "") == "question_submit":
                self.message = f"Submitted: {getattr(intent, 'text', '')}"
            elif getattr(intent, "kind", "") == "question_cancel":
                self.message = "Cancelled"
        return result


def build_app() -> Tui:
    tui = Tui()
    app = QuestionDialogApp()
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
