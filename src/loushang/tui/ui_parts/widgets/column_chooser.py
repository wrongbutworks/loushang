from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
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
from loushang.tui.ui_parts.widgets._utils import style_text

__all__ = [
    "ColumnChooser",
    "ColumnChooserClose",
    "ColumnChooserColumn",
    "ColumnChooserMove",
    "ColumnChooserSelect",
    "ColumnChooserSort",
    "ColumnChooserToggle",
    "ColumnChooserWidthChange",
]

ColumnMoveDirection = Literal["up", "down"]


@dataclass(frozen=True, slots=True)
class ColumnChooserColumn:
    key: str
    label: str
    visible: bool = True
    width: int | None = None
    fixed: bool = False
    sortable: bool = True
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class ColumnChooserToggle:
    column_key: str


@dataclass(frozen=True, slots=True)
class ColumnChooserMove:
    column_key: str
    direction: ColumnMoveDirection


@dataclass(frozen=True, slots=True)
class ColumnChooserWidthChange:
    column_key: str
    delta: int


@dataclass(frozen=True, slots=True)
class ColumnChooserSort:
    column_key: str


@dataclass(frozen=True, slots=True)
class ColumnChooserSelect:
    column_key: str


@dataclass(frozen=True, slots=True)
class ColumnChooserClose:
    pass


@dataclass(slots=True)
class ColumnChooser:
    columns: Sequence[ColumnChooserColumn]
    active_key: str | None = None
    empty_text: str = "No columns"
    theme: ThemeResolver | None = None
    focused: bool = False
    _active_index: int = field(default=0, init=False, repr=False)
    _first_visible_index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.set_columns(self.columns, active_key=self.active_key)

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def set_columns(
        self,
        columns: Sequence[ColumnChooserColumn],
        *,
        active_key: str | None = None,
    ) -> None:
        normalized = tuple(columns)
        keys: set[str] = set()
        for column in normalized:
            if not column.key:
                raise ValueError("column key must not be empty")
            if column.key in keys:
                raise ValueError(f"duplicate column key: {column.key}")
            keys.add(column.key)
        self.columns = normalized
        preferred_key = active_key if active_key is not None else self.active_key
        self._active_index = _nearest_column_index(normalized, preferred_key)
        active_column = self._active_column()
        self.active_key = None if active_column is None else active_column.key
        self._first_visible_index = min(self._first_visible_index, max(0, len(self.columns) - 1))

    def handle_input(self, event: object) -> object:
        kind = getattr(event, "kind", "")
        key = normalize_key_id(getattr(event, "key", "")) if kind == "key" else ""
        text = getattr(event, "text", "") if kind == "text" else ""
        command = key or text

        if key == "up":
            return self._move_active(-1)
        if key == "down":
            return self._move_active(1)
        if key == "home":
            return self._jump_active(first=True)
        if key == "end":
            return self._jump_active(first=False)
        if key == "enter":
            column = self._active_column()
            return None if column is None else ColumnChooserSelect(column.key)
        if key == "escape":
            return ColumnChooserClose()
        if command in {"space", " "}:
            column = self._active_column()
            return None if column is None or column.disabled else ColumnChooserToggle(column.key)
        if command == "[":
            column = self._active_column()
            return None if column is None or column.disabled else ColumnChooserWidthChange(column.key, -1)
        if command == "]":
            column = self._active_column()
            return None if column is None or column.disabled else ColumnChooserWidthChange(column.key, 1)
        if command in {"ctrl+up", "ctrl-up", "ctrl_up"}:
            column = self._active_column()
            return None if column is None or column.disabled else ColumnChooserMove(column.key, "up")
        if command in {"ctrl+down", "ctrl-down", "ctrl_down"}:
            column = self._active_column()
            return None if column is None or column.disabled else ColumnChooserMove(column.key, "down")
        if command == "s":
            column = self._active_column()
            if column is None or column.disabled or not column.sortable:
                return None
            return ColumnChooserSort(column.key)
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        height = max(0, constraints.max_height)
        if height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        if not self.columns:
            empty = truncate_to_width(self.empty_text, max_width=target_width, ellipsis="")
            return RenderResult.from_lines(
                [RenderLine(style_text(empty, self.theme, "widget.columnChooser.empty"))],
                constraints=constraints,
            )

        self._ensure_active_visible(height)
        visible = self.columns[self._first_visible_index : self._first_visible_index + height]
        lines: list[RenderLine] = []
        cursor: CursorDeclaration | None = None
        for offset, column in enumerate(visible):
            index = self._first_visible_index + offset
            active = self.focused and index == self._active_index
            if active:
                cursor = CursorDeclaration(row=offset, column=0)
            line = _column_line(column, active=active, width=target_width)
            token = _column_token(column, active=active)
            lines.append(RenderLine(style_text(line, self.theme, token)))
        return RenderResult.from_lines(lines, constraints=constraints, cursor=cursor)

    def _active_column(self) -> ColumnChooserColumn | None:
        if self._active_index < 0 or self._active_index >= len(self.columns):
            return None
        return self.columns[self._active_index]

    def _move_active(self, delta: int) -> bool:
        if not self.columns:
            return False
        next_index = max(0, min(len(self.columns) - 1, self._active_index + delta))
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        active_column = self._active_column()
        self.active_key = None if active_column is None else active_column.key
        return True

    def _jump_active(self, *, first: bool) -> bool:
        if not self.columns:
            return False
        next_index = 0 if first else len(self.columns) - 1
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        active_column = self._active_column()
        self.active_key = None if active_column is None else active_column.key
        return True

    def _ensure_active_visible(self, height: int) -> None:
        if height <= 0:
            return
        if self._active_index < self._first_visible_index:
            self._first_visible_index = self._active_index
        elif self._active_index >= self._first_visible_index + height:
            self._first_visible_index = self._active_index - height + 1


def _nearest_column_index(columns: tuple[ColumnChooserColumn, ...], active_key: str | None) -> int:
    if not columns:
        return 0
    if active_key is not None:
        for index, column in enumerate(columns):
            if column.key == active_key:
                return index
    return 0


def _column_line(column: ColumnChooserColumn, *, active: bool, width: int) -> str:
    prefix = "> " if active else "  "
    visibility = "x" if column.visible else " "
    label = _pad_visible(truncate_to_width(column.label, max_width=16, ellipsis=""), 16)
    width_text = "auto" if column.width is None else str(column.width)
    line = f"{prefix}[{visibility}] {label}  width {width_text:<3}"
    if column.fixed:
        line += " fixed"
    elif column.sortable:
        line += "      "
    if column.sortable:
        line += " sort"
    return truncate_to_width(line, max_width=width, ellipsis="")


def _column_token(column: ColumnChooserColumn, *, active: bool) -> str:
    if column.disabled:
        return "widget.columnChooser.disabled"
    if active:
        return "widget.columnChooser.focus"
    if not column.visible:
        return "widget.columnChooser.hidden"
    return "widget.columnChooser.row"


def _pad_visible(text: str, width: int) -> str:
    return f"{text}{' ' * max(0, width - visible_width(text))}"
