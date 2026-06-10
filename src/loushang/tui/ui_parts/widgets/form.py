from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult


@dataclass(frozen=True, slots=True)
class FormValidationResult:
    errors: dict[str, str]

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class FormRow:
    field_id: str
    control: object
    validator: Callable[[object], str | None] | None = None
    value_getter: Callable[[object], object] | None = None
    error: str = ""


@dataclass(slots=True)
class Form:
    rows: list[FormRow] | tuple[FormRow, ...]
    focused: bool = False
    _active_index: int = field(default=0, init=False, repr=False)

    def focus(self) -> None:
        self.focused = True
        self._focus_active()

    def blur(self) -> None:
        self.focused = False
        active = self._active_control()
        blur = getattr(active, "blur", None)
        if callable(blur):
            blur()

    def focus_next(self, wrap: bool = True) -> bool:
        return self._move_focus(1, wrap=wrap)

    def focus_previous(self, wrap: bool = True) -> bool:
        return self._move_focus(-1, wrap=wrap)

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = getattr(event, "key", "")
            if key == "tab":
                return self.focus_next()
            if key == "shift+tab":
                return self.focus_previous()
        active = self._active_control()
        handler = getattr(active, "handle_input", None)
        if callable(handler):
            return handler(event)
        return None

    def editor_input_target(self) -> object | None:
        from loushang.tui.framework import EditorInputTargetProvider

        active = self._active_control()
        if isinstance(active, EditorInputTargetProvider):
            return active.editor_input_target()
        return None

    def values(self) -> dict[str, object]:
        return {row.field_id: self._row_value(row) for row in self.rows}

    def validate(self) -> FormValidationResult:
        errors: dict[str, str] = {}
        for row in self.rows:
            if row.validator is None:
                row.error = ""
                continue
            error = row.validator(self._row_value(row))
            row.error = error or ""
            if error:
                errors[row.field_id] = error
        return FormValidationResult(errors=errors)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        lines: list[RenderLine] = []
        for row in self.rows:
            if len(lines) >= constraints.max_height:
                break
            render = getattr(row.control, "render", None)
            if callable(render):
                result = render(RenderConstraints(width=constraints.width, max_height=constraints.max_height - len(lines)))
                lines.extend(result.lines[: constraints.max_height - len(lines)])
            if row.error and len(lines) < constraints.max_height:
                lines.append(RenderLine(truncate_to_width(row.error, max_width=target_width, ellipsis="")))
        return RenderResult.from_lines(lines, constraints=constraints)

    def _active_control(self) -> object | None:
        if not self.rows:
            return None
        return self.rows[self._active_index].control

    def _focus_active(self) -> None:
        if not self.rows:
            return
        self._active_index = self._nearest_focusable_index(self._active_index, direction=1, wrap=True)
        active = self._active_control()
        focus = getattr(active, "focus", None)
        if callable(focus):
            focus()

    def _move_focus(self, delta: int, *, wrap: bool) -> bool:
        if not self.rows:
            return False
        previous = self._active_index
        next_index = self._next_focusable_index(previous, delta=delta, wrap=wrap)
        if next_index is None:
            return False
        if next_index == previous:
            return False
        previous_control = self.rows[previous].control
        blur = getattr(previous_control, "blur", None)
        if callable(blur):
            blur()
        self._active_index = next_index
        focus = getattr(self.rows[next_index].control, "focus", None)
        if callable(focus):
            focus()
        return True

    def _next_focusable_index(self, index: int, *, delta: int, wrap: bool) -> int | None:
        current = index
        for _ in range(len(self.rows)):
            current += delta
            if wrap:
                current %= len(self.rows)
            elif current < 0 or current >= len(self.rows):
                return None
            if _is_focusable(self.rows[current].control):
                return current
        return None

    def _nearest_focusable_index(self, index: int, *, direction: int, wrap: bool) -> int:
        if _is_focusable(self.rows[index].control):
            return index
        next_index = self._next_focusable_index(index, delta=direction, wrap=wrap)
        return index if next_index is None else next_index

    def _row_value(self, row: FormRow) -> object:
        if row.value_getter is not None:
            return row.value_getter(row.control)
        for attr in ("value", "checked", "selected_value"):
            if hasattr(row.control, attr):
                return getattr(row.control, attr)
        return row.control


def _is_focusable(control: object) -> bool:
    return all(callable(getattr(control, name, None)) for name in ("focus", "blur"))
