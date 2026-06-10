from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import callback_result, is_activation_event

TableAlign = Literal["left", "right"]
TABLE_SEPARATOR = "  "


@dataclass(frozen=True, slots=True)
class TableColumn:
    key: str
    header: str
    width: int | None = None
    min_width: int = 1
    align: TableAlign = "left"

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_width", max(0, self.min_width))
        if self.width is not None:
            object.__setattr__(self, "width", max(0, self.width))


@dataclass(frozen=True, slots=True)
class TableRow:
    value: str
    cells: Mapping[str, object] | Sequence[object]
    disabled: bool = False
    on_select: Callable[[], object] | None = None


@dataclass(frozen=True, slots=True)
class _NormalizedRow:
    value: str
    cells: tuple[str, ...]
    disabled: bool
    on_select: Callable[[], object] | None


@dataclass(slots=True)
class Table:
    columns: Sequence[TableColumn]
    rows: Sequence[TableRow | Mapping[str, object] | Sequence[object]]
    active_index: int = 0
    show_header: bool = True
    empty_text: str = "No rows"
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
    _columns: tuple[TableColumn, ...] = field(default=(), init=False, repr=False)
    _rows: tuple[_NormalizedRow, ...] = field(default=(), init=False, repr=False)
    _active_index: int = field(default=0, init=False, repr=False)
    _first_visible_index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._columns = tuple(self.columns)
        self._rows = tuple(_normalize_row(index, row, self._columns) for index, row in enumerate(self.rows))
        self._active_index = self._nearest_enabled_index(self.active_index)

    @property
    def active_value(self) -> str:
        row = self._active_row()
        return "" if row is None else row.value

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = getattr(event, "key", "")
            if key == "up":
                return self._move_active(-1)
            if key == "down":
                return self._move_active(1)
            if key == "home":
                return self._jump_active(first=True)
            if key == "end":
                return self._jump_active(first=False)
        if is_activation_event(event):
            return self._activate()
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        line = truncate_to_width(self.empty_text, max_width=target_width, ellipsis="")
        return RenderResult.from_lines([RenderLine(line)], constraints=constraints)

    def _enabled_indices(self) -> tuple[int, ...]:
        return tuple(index for index, row in enumerate(self._rows) if not row.disabled)

    def _nearest_enabled_index(self, preferred: int) -> int:
        enabled = self._enabled_indices()
        if not enabled:
            return 0
        preferred = max(0, min(preferred, len(self._rows) - 1))
        if preferred in enabled:
            return preferred
        for index in enabled:
            if index > preferred:
                return index
        return enabled[0]

    def _active_row(self) -> _NormalizedRow | None:
        if self._active_index < 0 or self._active_index >= len(self._rows):
            return None
        row = self._rows[self._active_index]
        return None if row.disabled else row

    def _move_active(self, delta: int) -> bool | None:
        enabled = self._enabled_indices()
        if not enabled:
            return None
        if self._active_index not in enabled:
            self._active_index = enabled[0]
            return True
        position = enabled.index(self._active_index)
        next_position = position + delta
        if self.wrap:
            next_position %= len(enabled)
        elif next_position < 0 or next_position >= len(enabled):
            return False
        next_index = enabled[next_position]
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        return True

    def _jump_active(self, *, first: bool) -> bool | None:
        enabled = self._enabled_indices()
        if not enabled:
            return None
        target = enabled[0] if first else enabled[-1]
        if target == self._active_index:
            return False
        self._active_index = target
        return True

    def _activate(self) -> object:
        row = self._active_row()
        if row is None:
            return None
        if row.on_select is not None:
            return callback_result(row.on_select())
        return row.value


def _normalize_row(
    index: int,
    row: TableRow | Mapping[str, object] | Sequence[object],
    columns: Sequence[TableColumn],
) -> _NormalizedRow:
    if isinstance(row, TableRow):
        cells = _cells_from_source(row.cells, columns)
        return _NormalizedRow(str(row.value), cells, row.disabled, row.on_select)
    cells = _cells_from_source(row, columns)
    return _NormalizedRow(_default_row_value(index, row, columns), cells, False, None)


def _cells_from_source(source: Mapping[str, object] | Sequence[object], columns: Sequence[TableColumn]) -> tuple[str, ...]:
    if isinstance(source, Mapping):
        return tuple("" if source.get(column.key) is None else str(source.get(column.key)) for column in columns)
    return tuple("" if index >= len(source) or source[index] is None else str(source[index]) for index, _ in enumerate(columns))


def _default_row_value(index: int, row: Mapping[str, object] | Sequence[object], columns: Sequence[TableColumn]) -> str:
    if isinstance(row, Mapping):
        for column in columns:
            value = row.get(column.key)
            if value is not None and str(value) != "":
                return str(value)
        return str(index)
    if row:
        value = row[0]
        if value is not None and str(value) != "":
            return str(value)
    return str(index)
