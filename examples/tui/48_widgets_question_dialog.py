from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    FocusableMixin,
    InputEvent,
    QuestionDialog,
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
QUESTION_DIALOG_EXAMPLE_THEME = ThemeResolver(
    defaults={
        "widget.question.action": {"color": "white"},
        "widget.question.focus": {"bold": True, "color": "cyan"},
        "widget.question.text": {"color": "cyan"},
        "widget.question.title": {"bold": True},
        "widget.textArea.placeholder": {"color": "bright_black"},
        "widget.textArea.text": {"color": "white"},
    }
)


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


@dataclass(slots=True)
class QuestionDialogApp(FocusableMixin):
    dialog: QuestionDialog = field(
        default_factory=lambda: QuestionDialog(
            title="Add note",
            question="What should be remembered?",
            placeholder="Write a multi-line answer",
            help_text="Enter adds a line. Tab to Submit/Cancel.",
            required=True,
            theme=QUESTION_DIALOG_EXAMPLE_THEME,
        )
    )
    recent_notes: tuple[str, ...] = (
        "Cache deploy checklist",
        "Follow up on flaky test",
    )
    status: str = "Drafting"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.dialog.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        prefix = [
            RenderLine(truncate_to_width("Notes Inbox", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            RenderLine("Recent"),
            *(
                RenderLine(truncate_to_width(f"  {note}", max_width=constraints.width, ellipsis=""))
                for note in self.recent_notes[:2]
            ),
            RenderLine(""),
            RenderLine("New Note"),
        ]
        body = self.dialog.render(
            RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - len(prefix) - 4))
        )
        rows = [
            *prefix,
            *body.lines,
            RenderLine(""),
            _field("Status", self.status, width=constraints.width),
            RenderLine(""),
            RenderLine(
                truncate_to_width(
                    "Escape cancels. [tab] buttons  [enter] choose  [q] quit",
                    max_width=constraints.width,
                    ellipsis="",
                )
            ),
        ]
        visible_rows = rows[: constraints.max_height]
        cursor = None
        if body.cursor is not None:
            cursor_row = body.cursor.row + len(prefix)
            if cursor_row < len(visible_rows):
                cursor = CursorDeclaration(row=cursor_row, column=body.cursor.column)
        return RenderResult.from_lines(visible_rows, constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        result = self.dialog.handle_input(event)
        intents = result if isinstance(result, tuple) else (() if result is None else (result,))
        for intent in intents:
            if getattr(intent, "kind", "") == "question_submit":
                text = getattr(intent, "text", "")
                self.recent_notes = (text, *self.recent_notes)
                self.status = f"Submitted: {text}"
            elif getattr(intent, "kind", "") == "question_cancel":
                self.status = "Cancelled"
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
