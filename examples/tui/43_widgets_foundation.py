from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    Checkbox,
    Choice,
    ConfirmDialog,
    CursorDeclaration,
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
    truncate_to_width,
)

FIELD_LABEL_WIDTH = 14
FIELD_LABELS = {
    "name": "Name",
    "cache": "Cache",
    "mode": "Mode",
    "auto": "Approval",
    "model": "Model",
}


@dataclass(slots=True)
class WidgetsApp(FocusableMixin):
    form: Form = field(default_factory=lambda: Form(_rows()))
    message: str = "Edit fields with the keyboard."
    open_confirm: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.form.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [RenderLine("Loushang TUI Widgets"), RenderLine("")]
        form_start_row = len(rows)
        form_result = _render_form_grid(
            self.form,
            RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 5)),
        )
        rows.extend(form_result.lines)
        rows.extend(
            [
                RenderLine(""),
                RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
                RenderLine(truncate_to_width("[tab] field  [up/down] option  [space] toggle/select  [ctrl+s] confirm  [q] quit", max_width=constraints.width, ellipsis="")),
            ]
        )
        cursor = None
        if form_result.cursor is not None:
            cursor = CursorDeclaration(
                row=form_start_row + form_result.cursor.row,
                column=form_result.cursor.column,
            )
            if cursor.row >= min(len(rows), constraints.max_height):
                cursor = None
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

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
        FormRow("name", TextField(value="tower")),
        FormRow("cache", Checkbox("Enable cache", checked=True)),
        FormRow("mode", RadioGroup([Choice("fast", "Fast"), Choice("safe", "Safe")], value="fast", orientation="horizontal")),
        FormRow("auto", Toggle("Auto approve")),
        FormRow("model", SelectList([SelectItem("Kimi"), SelectItem("Qwen")], max_visible=2)),
    ]


def _render_form_grid(form: Form, constraints: RenderConstraints) -> RenderResult:
    lines: list[RenderLine] = []
    cursor: CursorDeclaration | None = None
    control_width = max(1, constraints.width - FIELD_LABEL_WIDTH)
    for row in form.rows:
        if len(lines) >= constraints.max_height:
            break
        render = getattr(row.control, "render", None)
        if not callable(render):
            continue
        start_row = len(lines)
        result = render(RenderConstraints(width=control_width, max_height=constraints.max_height - len(lines)))
        rendered_lines = result.lines[: constraints.max_height - len(lines)]
        for index, line in enumerate(rendered_lines):
            label = FIELD_LABELS.get(row.field_id, row.field_id) if index == 0 else ""
            text = truncate_to_width(f"{label:<{FIELD_LABEL_WIDTH}}{line.text}", max_width=constraints.width, ellipsis="")
            lines.append(RenderLine(text))
        if getattr(row.control, "focused", False) and result.cursor is not None and result.cursor.row < len(rendered_lines):
            cursor = CursorDeclaration(
                row=start_row + result.cursor.row,
                column=FIELD_LABEL_WIDTH + result.cursor.column,
            )
    return RenderResult.from_lines(lines, constraints=constraints, cursor=cursor)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
