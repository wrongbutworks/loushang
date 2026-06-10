from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    Checkbox,
    Choice,
    ConfirmDialog,
    FocusableMixin,
    Form,
    FormRow,
    InputEvent,
    RadioGroup,
    RenderConstraints,
    RenderLine,
    RenderResult,
    SelectItem,
    SelectList,
    TextField,
    Toggle,
    Tui,
    TuiInputResult,
    TuiRunner,
)


@dataclass(slots=True)
class WidgetsApp(FocusableMixin):
    form: Form = field(default_factory=lambda: Form(_rows()))
    message: str = "Edit fields with the keyboard."
    open_confirm: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        super().__init__()
        self.form.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [RenderLine("Loushang TUI Widgets"), RenderLine("")]
        form_result = self.form.render(RenderConstraints(width=constraints.width, max_height=max(0, constraints.max_height - 5)))
        rows.extend(form_result.lines)
        rows.extend(
            [
                RenderLine(""),
                RenderLine(self.message[: constraints.width]),
                RenderLine("[tab] move  [ctrl+s] confirm  [q] quit"),
            ]
        )
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=form_result.cursor)

    def handle_input(self, event: Any) -> object:
        if not isinstance(event, InputEvent):
            return None
        if event.kind == "key" and event.key == "ctrl+s":
            self.message = "Confirming settings..."
            if self.open_confirm is not None:
                self.open_confirm()
            return True
        result = self.form.handle_input(event)
        if result:
            self.message = f"Values: {self.form.values()}"
        return result

    def editor_input_target(self) -> object | None:
        return self.form.editor_input_target()


def build_app() -> Tui:
    tui = Tui()
    app = WidgetsApp()

    def open_confirm() -> None:
        dialog = ConfirmDialog(title="Apply widget settings?", body="Press enter to apply or escape to cancel.")
        tui.show_overlay(dialog, focus_target=dialog, presentation="modal", anchor="center", width="80%")

    app.open_confirm = open_confirm
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


def _rows() -> list[FormRow]:
    return [
        FormRow("name", TextField(label="Name", value="tower")),
        FormRow("cache", Checkbox("Enable cache", checked=True)),
        FormRow("mode", RadioGroup([Choice("fast", "Fast"), Choice("safe", "Safe")], value="fast")),
        FormRow("auto", Toggle("Auto approve")),
        FormRow("model", SelectList([SelectItem("Kimi"), SelectItem("Qwen")], max_visible=2)),
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
