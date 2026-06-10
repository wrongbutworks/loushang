from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import (
    callback_result,
    is_activation_event,
    style_text,
)

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
        height = max(0, constraints.max_height)
        if height == 0:
            return RenderResult.from_lines([], constraints=constraints)
        if not self._columns:
            empty = truncate_to_width(self.empty_text, max_width=target_width, ellipsis="")
            return RenderResult.from_lines(
                [RenderLine(style_text(empty, self.theme, "widget.table.empty"))],
                constraints=constraints,
            )

        widths = _column_widths(self._columns, target_width)
        prefix_width = min(2, target_width)
        lines: list[RenderLine] = []
        if self.show_header and len(lines) < height:
            lines.append(RenderLine(_table_header_line(self, widths, prefix_width, target_width)))

        body_height = max(0, height - len(lines))
        if self._rows:
            self._ensure_active_visible(body_height)
            indexed_rows = tuple(enumerate(self._rows))
            visible_rows = indexed_rows[self._first_visible_index : self._first_visible_index + body_height]
            for index, row in visible_rows:
                lines.append(RenderLine(_table_body_line(self, index, row, widths, prefix_width, target_width)))
        elif len(lines) < height:
            lines.append(RenderLine(_table_empty_line(self, widths, prefix_width, target_width)))
        return RenderResult.from_lines(lines[:height], constraints=constraints)

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

    def _ensure_active_visible(self, height: int) -> None:
        if height <= 0 or not self._rows:
            return
        if self._active_index < self._first_visible_index:
            self._first_visible_index = self._active_index
        elif self._active_index >= self._first_visible_index + height:
            self._first_visible_index = self._active_index - height + 1
        max_first = max(0, len(self._rows) - height)
        self._first_visible_index = max(0, min(self._first_visible_index, max_first))


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


def _column_widths(columns: Sequence[TableColumn], target_width: int) -> tuple[int, ...]:
    if not columns or target_width <= 0:
        return tuple(0 for _ in columns)
    prefix_width = min(2, target_width)
    grid_width = max(0, target_width - prefix_width)
    if grid_width == 0:
        return tuple(0 for _ in columns)

    widths: list[int] = []
    flexible_indices: list[int] = []
    for index, column in enumerate(columns):
        if column.width is None:
            widths.append(column.min_width)
            flexible_indices.append(index)
        else:
            widths.append(max(column.width, column.min_width))

    remaining = grid_width - _occupied_grid_width(widths)
    if remaining > 0 and flexible_indices:
        base, remainder = divmod(remaining, len(flexible_indices))
        for offset, index in enumerate(flexible_indices):
            widths[index] += base + (1 if offset < remainder else 0)
    if _occupied_grid_width(widths) > grid_width:
        widths = _shrink_widths_to_fit(widths, grid_width)
    return tuple(widths)


def _occupied_grid_width(widths: Sequence[int]) -> int:
    visible_count = sum(1 for width in widths if width > 0)
    separator_width = max(0, visible_count - 1) * len(TABLE_SEPARATOR)
    return sum(max(0, width) for width in widths) + separator_width


def _shrink_widths_to_fit(widths: Sequence[int], grid_width: int) -> list[int]:
    result = [max(0, width) for width in widths]
    overflow = _occupied_grid_width(result) - max(0, grid_width)
    while overflow > 0 and any(width > 0 for width in result):
        for index in range(len(result) - 1, -1, -1):
            if result[index] <= 0:
                continue
            reduction = min(result[index], overflow)
            result[index] -= reduction
            overflow = _occupied_grid_width(result) - max(0, grid_width)
            if overflow <= 0:
                break
    return result


def _table_header_line(table: Table, widths: Sequence[int], prefix_width: int, target_width: int) -> str:
    prefix = " " * prefix_width
    cells = _join_cells(tuple(column.header for column in table._columns), widths, table._columns)
    line = truncate_to_width(f"{prefix}{cells}", max_width=target_width, ellipsis="")
    return style_text(line, table.theme, "widget.table.header")


def _table_body_line(
    table: Table,
    index: int,
    row: _NormalizedRow,
    widths: Sequence[int],
    prefix_width: int,
    target_width: int,
) -> str:
    is_focused_row = table.focused and index == table._active_index and not row.disabled
    prefix_text = "> " if is_focused_row else "  "
    prefix = truncate_to_width(prefix_text, max_width=prefix_width, ellipsis="")
    cells = _join_cells(row.cells, widths, table._columns)
    line = truncate_to_width(f"{prefix}{cells}", max_width=target_width, ellipsis="")
    token = (
        "widget.table.disabled"
        if row.disabled
        else "widget.table.focus"
        if is_focused_row
        else "widget.table.row"
    )
    return style_text(line, table.theme, token)


def _table_empty_line(table: Table, widths: Sequence[int], prefix_width: int, target_width: int) -> str:
    prefix = " " * prefix_width
    cells = _join_cells((table.empty_text,) + tuple("" for _ in table._columns[1:]), widths, table._columns)
    line = truncate_to_width(f"{prefix}{cells}", max_width=target_width, ellipsis="")
    return style_text(line, table.theme, "widget.table.empty")


def _format_cell(text: str, width: int, align: TableAlign, *, pad_right: bool = True) -> str:
    if width <= 0:
        return ""
    clipped = truncate_to_width(text, max_width=width, ellipsis="")
    padding = " " * max(0, width - visible_width(clipped))
    if align == "right":
        return f"{padding}{clipped}"
    return f"{clipped}{padding}" if pad_right else clipped


def _join_cells(cells: Sequence[str], widths: Sequence[int], columns: Sequence[TableColumn]) -> str:
    rendered: list[str] = []
    visible_cells = [
        (cell, width, column) for cell, width, column in zip(cells, widths, columns, strict=True) if width > 0
    ]
    for offset, (cell, width, column) in enumerate(visible_cells):
        rendered.append(_format_cell(cell, width, column.align, pad_right=offset < len(visible_cells) - 1))
    return TABLE_SEPARATOR.join(rendered)
