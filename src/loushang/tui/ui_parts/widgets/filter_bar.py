from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
    strip_control_sequences,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import (
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
)
from loushang.tui.keybindings import normalize_key_id
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.text_input import TextInput
from loushang.tui.ui_parts.widgets._utils import style_text

__all__ = [
    "FilterApply",
    "FilterBar",
    "FilterBoundary",
    "FilterField",
    "FilterFocusChange",
]


@dataclass(frozen=True, slots=True)
class FilterField:
    key: str
    label: str
    width: int
    value: str = ""
    row: int = 0
    placeholder: str = ""


@dataclass(frozen=True, slots=True)
class FilterApply:
    values: dict[str, str]
    active_key: str


@dataclass(frozen=True, slots=True)
class FilterFocusChange:
    active_key: str
    previous_key: str


@dataclass(frozen=True, slots=True)
class FilterBoundary:
    direction: Literal["forward", "backward"]
    active_key: str
    values: dict[str, str]


@dataclass(slots=True)
class FilterBar:
    fields: Sequence[FilterField]
    row_details: Mapping[int, str] | None = None
    active_key: str | None = None
    theme: ThemeResolver | None = None
    focused: bool = False
    _inputs: dict[str, TextInput] = field(init=False, repr=False)
    _fields_by_key: dict[str, FilterField] = field(init=False, repr=False)
    _field_keys: tuple[str, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("FilterBar requires at least one field")
        fields_by_key: dict[str, FilterField] = {}
        inputs: dict[str, TextInput] = {}
        keys: list[str] = []
        for item in self.fields:
            if not item.key:
                raise ValueError("filter field key must not be empty")
            if item.key in fields_by_key:
                raise ValueError(f"duplicate filter field key: {item.key}")
            if item.width <= 0:
                raise ValueError("filter field width must be positive")
            if item.row < 0:
                raise ValueError("filter field row must be non-negative")
            fields_by_key[item.key] = item
            keys.append(item.key)
            text_input = TextInput(placeholder=item.placeholder, theme=self.theme)
            text_input.set_text(item.value)
            inputs[item.key] = text_input
        self._fields_by_key = fields_by_key
        self._inputs = inputs
        self._field_keys = tuple(keys)
        if self.active_key is not None and self.active_key not in fields_by_key:
            raise ValueError(f"unknown active filter field: {self.active_key}")
        if self.focused:
            self.focus(self.active_key)

    @property
    def values(self) -> dict[str, str]:
        return {key: self._inputs[key].value for key in self._field_keys}

    def focus(self, key: str | None = None) -> None:
        target_key = key or self.active_key or self._field_keys[0]
        if target_key not in self._fields_by_key:
            raise ValueError(f"unknown filter field: {target_key}")
        self.focused = True
        self.active_key = target_key
        for item_key, text_input in self._inputs.items():
            if item_key == target_key:
                text_input.focus()
                text_input.set_selection(0, len(text_input.value))
            else:
                text_input.blur()

    def blur(self) -> None:
        self.focused = False
        for text_input in self._inputs.values():
            text_input.blur()

    def set_value(self, key: str, value: str) -> None:
        self._input(key).set_text(value)

    def set_values(self, values: Mapping[str, str]) -> None:
        for key, value in values.items():
            self.set_value(key, value)

    def editor_input_target(self) -> object | None:
        active = self._active_input()
        if active is None:
            return None
        return active.editor_input_target()

    def handle_input(self, event: object) -> object:
        active_key = self.active_key or self._field_keys[0]
        if getattr(event, "kind", "") == "key":
            key = normalize_key_id(getattr(event, "key", ""))
            if key == "enter":
                return FilterApply(values=self.values, active_key=active_key)
            if key == "tab":
                return self._move_focus(1)
            if key == "shift+tab":
                return self._move_focus(-1)
        active = self._active_input()
        if active is None:
            return False
        return active.handle_input(event)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        lines: list[RenderLine] = []
        cursor: CursorDeclaration | None = None
        rows = self._row_numbers()

        for row_number in rows[: constraints.max_height]:
            row_index = len(lines)
            row_fields = self._fields_for_row(row_number)
            prefix = "> " if self.focused and self.active_key in {item.key for item in row_fields} else "  "
            line, active_column = self._render_row(row_fields, row_number=row_number, prefix=prefix, width=target_width)
            lines.append(RenderLine(style_text(line, self.theme, "widget.filterBar")))
            if active_column is not None and active_column <= visible_width(line):
                cursor = CursorDeclaration(row=row_index, column=active_column)

        return RenderResult.from_lines(lines, constraints=constraints, cursor=cursor)

    def _move_focus(self, delta: Literal[-1, 1]) -> FilterFocusChange | FilterBoundary:
        current_key = self.active_key or self._field_keys[0]
        current_index = self._field_keys.index(current_key)
        next_index = current_index + delta
        if next_index < 0:
            self.focus(current_key)
            return FilterBoundary(direction="backward", active_key=current_key, values=self.values)
        if next_index >= len(self._field_keys):
            self.focus(current_key)
            return FilterBoundary(direction="forward", active_key=current_key, values=self.values)
        next_key = self._field_keys[next_index]
        self.focus(next_key)
        return FilterFocusChange(active_key=next_key, previous_key=current_key)

    def _active_input(self) -> TextInput | None:
        if not self.focused or self.active_key is None:
            return None
        return self._inputs.get(self.active_key)

    def _input(self, key: str) -> TextInput:
        if key not in self._inputs:
            raise ValueError(f"unknown filter field: {key}")
        return self._inputs[key]

    def _row_numbers(self) -> tuple[int, ...]:
        return tuple(sorted({item.row for item in self.fields}))

    def _fields_for_row(self, row_number: int) -> tuple[FilterField, ...]:
        return tuple(item for item in self.fields if item.row == row_number)

    def _render_row(
        self,
        fields: Sequence[FilterField],
        *,
        row_number: int,
        prefix: str,
        width: int,
    ) -> tuple[str, int | None]:
        parts: list[str] = []
        cursor_column: int | None = None
        offset = visible_width(prefix)
        for index, item in enumerate(fields):
            if index:
                parts.append("  ")
                offset += 2
            label_prefix = f"{item.label}: ["
            parts.append(label_prefix)
            offset += visible_width(label_prefix)
            input_result = self._input(item.key).render(RenderConstraints(width=item.width, max_height=1))
            input_text = input_result.lines[0].text if input_result.lines else ""
            input_text = _pad_visible(input_text, item.width)
            if item.key == self.active_key and self.focused and input_result.cursor is not None:
                cursor_column = offset + input_result.cursor.column
            parts.append(input_text)
            parts.append("]")
            offset += item.width + 1
        detail = "" if self.row_details is None else self.row_details.get(row_number, "")
        if detail:
            parts.append(f"  {detail}")

        line = truncate_to_width(f"{prefix}{''.join(parts)}", max_width=width, ellipsis="")
        return line, cursor_column


def _pad_visible(text: str, width: int) -> str:
    return f"{text}{' ' * max(0, width - visible_width(strip_control_sequences(text)))}"
