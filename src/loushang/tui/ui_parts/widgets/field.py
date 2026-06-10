from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import CursorDeclaration, RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.text_input import TextInput


@dataclass(init=False, slots=True)
class TextField:
    label: str
    placeholder: str
    help_text: str
    error: str
    on_submit: Callable[[str], object] | None
    on_escape: Callable[[], object] | None
    on_change: Callable[[str], object] | None
    theme: ThemeResolver | None
    focused: bool
    _input: TextInput = field(init=False, repr=False)

    def __init__(
        self,
        label: str = "",
        value: str = "",
        placeholder: str = "",
        help_text: str = "",
        error: str = "",
        on_submit: Callable[[str], object] | None = None,
        on_escape: Callable[[], object] | None = None,
        on_change: Callable[[str], object] | None = None,
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None:
        self.label = label
        self.placeholder = placeholder
        self.help_text = help_text
        self.error = error
        self.on_submit = on_submit
        self.on_escape = on_escape
        self.on_change = on_change
        self.theme = theme
        self.focused = focused
        self._input = TextInput(
            placeholder=placeholder,
            on_submit=on_submit,
            on_escape=on_escape,
            on_change=on_change,
            theme=theme,
            focused=focused,
        )
        self._input.set_text(value)

    @property
    def value(self) -> str:
        return self._input.value

    def focus(self) -> None:
        self.focused = True
        self._input.focus()

    def blur(self) -> None:
        self.focused = False
        self._input.blur()

    def set_text(self, text: str) -> None:
        self._input.set_text(text)

    def clear(self) -> None:
        self._input.clear()

    def undo(self) -> bool:
        return self._input.undo()

    def redo(self) -> bool:
        return self._input.redo()

    def handle_input(self, event: object) -> object:
        return self._input.handle_input(event)

    def editor_input_target(self) -> object:
        return self._input.editor_input_target()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        lines: list[RenderLine] = []
        cursor: CursorDeclaration | None = None

        if self.label and len(lines) < constraints.max_height:
            lines.append(RenderLine(truncate_to_width(self.label, max_width=target_width, ellipsis="")))

        if len(lines) < constraints.max_height:
            input_row = len(lines)
            input_result = self._input.render(RenderConstraints(width=constraints.width, max_height=1))
            lines.extend(input_result.lines[: max(0, constraints.max_height - len(lines))])
            if input_result.cursor is not None and len(lines) > input_row:
                cursor = CursorDeclaration(
                    row=input_row + input_result.cursor.row,
                    column=input_result.cursor.column,
                )

        detail = self.error or self.help_text
        if detail and len(lines) < constraints.max_height:
            lines.append(RenderLine(truncate_to_width(detail, max_width=target_width, ellipsis="")))

        return RenderResult.from_lines(lines, constraints=constraints, cursor=cursor)
