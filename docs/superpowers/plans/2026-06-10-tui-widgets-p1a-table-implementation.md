# TUI Widgets P1A Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, keyboard-friendly `Table` widget for dense row/column data in `loushang.tui`.

**Architecture:** Implement `Table` as one focused widget module under `src/loushang/tui/ui_parts/widgets/table.py`. The widget follows the existing `Renderable` + local `Focusable` pattern used by `Menu`, `Tabs`, and `Toolbar`, with row normalization, width allocation, visible-window tracking, and theme application kept inside the module.

**Tech Stack:** Python 3.11+, dataclasses with slots, `loushang.tui.core.RenderResult`, `loushang.tui.cell_width` helpers, existing widget theme helpers, pytest, Ruff.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-10-tui-widgets-p1a-table-design.md`
- Existing patterns:
  - `src/loushang/tui/ui_parts/widgets/menu.py`
  - `src/loushang/tui/ui_parts/widgets/tabs.py`
  - `src/loushang/tui/ui_parts/widgets/display.py`
  - `tests/tui/test_widgets_light_controls.py`
  - `tests/tui/test_widgets_small_controls.py`

## File Structure

Create:

- `src/loushang/tui/ui_parts/widgets/table.py`
  - Owns `TableAlign`, `TableColumn`, `TableRow`, and `Table`.
  - Owns internal normalization, width allocation, row rendering, and input handling helpers.
- `tests/tui/test_widgets_table.py`
  - Focused table tests only.
- `examples/tui/46_widgets_table.py`
  - Small runnable table composition example.

Modify:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `Table`, `TableColumn`, `TableRow`, `TableAlign`.
- `src/loushang/tui/ui_parts/__init__.py`
  - Re-export the same stable API.
- `src/loushang/tui/__init__.py`
  - Re-export the same stable API.
- `docs/en/reference/tui-widgets.md`
  - Add P1A Table entry, short usage, theme tokens, and example link.
- `docs/zh-CN/reference/tui-widgets.md`
  - Mirror the English reference update.

Do not modify:

- `RenderLoop`, `InputRouter`, `SurfaceHost`, `TextInput`, or existing widget behavior.

---

### Task 1: Add Failing Table API And Normalization Tests

**Files:**
- Create: `tests/tui/test_widgets_table.py`

- [ ] **Step 1: Create the table test file with shared helpers**

Use the same helper style as existing widget tests:

```python
from __future__ import annotations

import runpy
from typing import Any

from loushang.tui import (
    InputEvent,
    RenderConstraints,
    Table,
    TableColumn,
    TableRow,
    ThemeResolver,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import Table as UiTable
from loushang.tui.ui_parts import TableColumn as UiTableColumn
from loushang.tui.ui_parts import TableRow as UiTableRow
from loushang.tui.ui_parts.widgets import Table as WidgetTable
from loushang.tui.ui_parts.widgets import TableColumn as WidgetTableColumn
from loushang.tui.ui_parts.widgets import TableRow as WidgetTableRow


def render_lines(part: Any, *, width: int = 60, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 60, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)
```

- [ ] **Step 2: Add failing public export tests**

```python
def test_table_widgets_are_reexported_from_public_modules() -> None:
    assert Table is UiTable
    assert Table is WidgetTable
    assert TableColumn is UiTableColumn
    assert TableColumn is WidgetTableColumn
    assert TableRow is UiTableRow
    assert TableRow is WidgetTableRow
    assert TableColumn("name", "Name").key == "name"
    assert TableRow("row-1", {"name": "Tower"}).value == "row-1"
```

- [ ] **Step 3: Add failing normalization tests**

```python
def test_table_normalizes_mapping_sequence_rows_and_column_config() -> None:
    table = Table(
        [
            TableColumn("name", "Name", width=-5, min_width=-1),
            TableColumn("status", "Status"),
        ],
        [
            {"name": "", "status": "ready"},
            {"name": None, "status": "idle"},
            ("coded", "done"),
        ],
    )

    assert table.handle_input(InputEvent(kind="key", key="enter")) == "0"
    assert table.handle_input(InputEvent(kind="key", key="down")) is True
    assert table.handle_input(InputEvent(kind="key", key="enter")) == "1"
    assert table.handle_input(InputEvent(kind="key", key="down")) is True
    assert table.handle_input(InputEvent(kind="key", key="enter")) == "coded"
    assert_widths_within(render_lines(table, width=12, height=4), 12)
```

- [ ] **Step 4: Run the focused test to verify it fails**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: FAIL during import because `Table`, `TableColumn`, and `TableRow` do not exist.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/tui/test_widgets_table.py
git commit -m "test(tui): add table widget api tests"
```

---

### Task 2: Implement Table API Skeleton And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/table.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_table.py`

- [ ] **Step 1: Create `table.py` with dataclasses and normalization skeleton**

Start with this module shape:

```python
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width, visible_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import callback_result, is_activation_event, style_text

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
```

- [ ] **Step 2: Add minimal focus, input, and render methods**

Implement enough behavior for Task 1 tests:

```python
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
        return RenderResult.from_lines(
            [RenderLine(truncate_to_width(self.empty_text, max_width=target_width, ellipsis=""))],
            constraints=constraints,
        )
```

Then add private helpers matching `Menu` semantics:

```python
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
```

- [ ] **Step 3: Implement row normalization helpers**

```python
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
```

- [ ] **Step 4: Add public exports**

In `src/loushang/tui/ui_parts/widgets/__init__.py`:

```python
from .table import Table as Table
from .table import TableAlign as TableAlign
from .table import TableColumn as TableColumn
from .table import TableRow as TableRow
```

Add those names to `__all__`.

Repeat the same import and `__all__` changes in:

- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: Task 1 tests pass. Later rendering tests do not exist yet.

- [ ] **Step 6: Run Ruff on touched production and test files**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui/ui_parts/widgets/table.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_table.py
```

Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/table.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py tests/tui/test_widgets_table.py
git commit -m "feat(tui): add table widget api"
```

---

### Task 3: Add And Implement Deterministic Table Rendering

**Files:**
- Modify: `tests/tui/test_widgets_table.py`
- Modify: `src/loushang/tui/ui_parts/widgets/table.py`

- [ ] **Step 1: Add failing rendering tests**

Add these tests:

```python
def test_table_renders_header_rows_fixed_flexible_widths_and_alignment() -> None:
    table = Table(
        [
            TableColumn("name", "Name", width=8),
            TableColumn("status", "Status"),
            TableColumn("count", "Count", width=5, align="right"),
        ],
        [
            TableRow("build", {"name": "Build", "status": "ready", "count": 12}),
            TableRow("deploy", {"name": "Deploy", "status": "blocked", "count": 3}),
        ],
    )

    assert plain_lines(table, width=34, height=4) == (
        "  Name      Status           Count",
        "  Build     ready               12",
        "  Deploy    blocked              3",
    )


def test_table_truncates_narrow_width_and_short_height() -> None:
    table = Table(
        [
            TableColumn("name", "Name", width=8),
            TableColumn("status", "Status"),
        ],
        [
            TableRow("one", {"name": "LongName", "status": "VeryLongStatus"}),
            TableRow("two", {"name": "Second", "status": "Done"}),
        ],
    )

    assert plain_lines(table, width=16, height=2) == (
        "  Name      Stat",
        "  LongName  Very",
    )
    assert_widths_within(render_lines(table, width=1, height=3), 1)


def test_table_column_widths_honor_min_width_then_shrink_right_to_left() -> None:
    table = Table(
        [
            TableColumn("id", "ID", width=1, min_width=3),
            TableColumn("name", "Name", min_width=4),
            TableColumn("note", "Note", width=20),
        ],
        [
            {"id": "ABCDE", "name": "WXYZ", "note": "tail"},
        ],
    )

    assert plain_lines(table, width=14, height=2) == (
        "  ID   Name  N",
        "  ABC  WXYZ  t",
    )


def test_table_empty_and_no_column_rendering() -> None:
    with_columns = Table([TableColumn("name", "Name")], [])
    no_columns = Table([], [])

    assert plain_lines(with_columns, width=12, height=3) == (
        "  Name",
        "  No rows",
    )
    assert plain_lines(no_columns, width=12, height=3) == ("No rows",)


def test_table_can_hide_header() -> None:
    table = Table(
        [TableColumn("name", "Name")],
        [TableRow("one", {"name": "One"})],
        show_header=False,
    )

    assert plain_lines(table, width=12, height=2) == ("  One",)
```

- [ ] **Step 2: Run focused tests to verify rendering tests fail**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: FAIL on the new rendering tests because `render()` still only returns `empty_text`.

- [ ] **Step 3: Implement column width allocation helpers**

Add private helpers in `table.py`:

```python
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
```

Adjust if tests show spacing differs. Keep the final behavior aligned with the spec: prefix budget first, separators second, fixed columns before flexible, remainder left-to-right, shrink right-to-left.

- [ ] **Step 4: Implement cell formatting and row rendering helpers**

```python
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
    visible_cells = [(cell, width, column) for cell, width, column in zip(cells, widths, columns, strict=True) if width > 0]
    for offset, (cell, width, column) in enumerate(visible_cells):
        rendered.append(_format_cell(cell, width, column.align, pad_right=offset < len(visible_cells) - 1))
    return TABLE_SEPARATOR.join(rendered)
```

- [ ] **Step 5: Replace `Table.render()` with full rendering**

Behavior to implement:

- Compute `target_width`.
- If no columns: return one themed empty line, truncated to width and height.
- Compute `widths = _column_widths(self._columns, target_width)`.
- If `show_header`: render header cells with `"  "` prefix truncated to `prefix_width`.
- Render a body window of rows after the header.
- If columns exist and rows are empty, render prefixed empty text after header if height remains.
- Always apply `truncate_to_width(full_line, max_width=target_width, ellipsis="")` at the end.

Skeleton:

```python
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
            visible = tuple(enumerate(self._rows))[self._first_visible_index : self._first_visible_index + body_height]
            for index, row in visible:
                lines.append(RenderLine(_table_body_line(self, index, row, widths, prefix_width, target_width)))
        elif len(lines) < height:
            lines.append(RenderLine(_table_empty_line(self, widths, prefix_width, target_width)))
        return RenderResult.from_lines(lines[:height], constraints=constraints)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/tui/test_widgets_table.py src/loushang/tui/ui_parts/widgets/table.py
git commit -m "feat(tui): render table rows and columns"
```

---

### Task 4: Add And Implement Navigation, Windowing, Disabled Rows, And Activation

**Files:**
- Modify: `tests/tui/test_widgets_table.py`
- Modify: `src/loushang/tui/ui_parts/widgets/table.py`

- [ ] **Step 1: Add failing navigation and activation tests**

```python
def test_table_navigation_activation_callbacks_and_space_forms() -> None:
    calls: list[str] = []
    table = Table(
        [TableColumn("name", "Name")],
        [
            TableRow("build", {"name": "Build"}, on_select=lambda: calls.append("build")),
            TableRow("disabled", {"name": "Disabled"}, disabled=True),
            TableRow("deploy", {"name": "Deploy"}, on_select=lambda: "deploy"),
        ],
    )
    table.focus()

    assert table.active_value == "build"
    assert plain_lines(table, width=20, height=4)[1] == "> Build"
    assert table.handle_input(InputEvent(kind="key", key="enter")) is True
    assert table.handle_input(InputEvent(kind="key", key="down")) is True
    assert table.active_value == "deploy"
    assert table.handle_input(InputEvent(kind="key", key="enter")) == "deploy"
    assert table.handle_input(InputEvent(kind="key", key="down")) is True
    assert table.active_value == "build"
    assert table.handle_input(InputEvent(kind="text", text=" ")) is True
    assert table.handle_input(InputEvent(kind="key", key="space")) is True
    assert calls == ["build", "build", "build"]


def test_table_wrap_false_boundaries_empty_disabled_and_height_window() -> None:
    table = Table(
        [TableColumn("name", "Name")],
        [
            TableRow("one", {"name": "One"}),
            TableRow("two", {"name": "Two"}),
            TableRow("three", {"name": "Three"}),
        ],
        wrap=False,
    )
    table.focus()

    assert table.handle_input(InputEvent(kind="key", key="up")) is False
    assert table.handle_input(InputEvent(kind="key", key="end")) is True
    assert table.active_value == "three"
    assert table.handle_input(InputEvent(kind="key", key="down")) is False
    assert table.handle_input(InputEvent(kind="key", key="home")) is True
    assert table.active_value == "one"

    assert Table([], []).handle_input(InputEvent(kind="key", key="down")) is None
    disabled = Table([TableColumn("name", "Name")], [TableRow("no", {"name": "No"}, disabled=True)])
    disabled.focus()
    assert disabled.handle_input(InputEvent(kind="key", key="down")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None

    windowed = Table(
        [TableColumn("name", "Name")],
        [TableRow(str(index), {"name": f"Item {index}"}) for index in range(5)],
        active_index=4,
    )
    windowed.focus()
    assert plain_lines(windowed, width=20, height=3) == (
        "  Name",
        "  Item 3",
        "> Item 4",
    )
```

- [ ] **Step 2: Run focused tests to verify failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: FAIL if body focus styling or height-window behavior is incomplete.

- [ ] **Step 3: Implement or tighten `_ensure_active_visible()`**

Use `Menu._ensure_active_visible()` semantics, but the height is body rows only:

```python
    def _ensure_active_visible(self, height: int) -> None:
        if height <= 0 or not self._rows:
            return
        if self._active_index < self._first_visible_index:
            self._first_visible_index = self._active_index
        elif self._active_index >= self._first_visible_index + height:
            self._first_visible_index = self._active_index - height + 1
        max_first = max(0, len(self._rows) - height)
        self._first_visible_index = max(0, min(self._first_visible_index, max_first))
```

- [ ] **Step 4: Verify body row styling and disabled row token selection**

`_table_body_line()` should choose:

- Prefix `"> "` only when `table.focused and index == table._active_index and not row.disabled`.
- Token `widget.table.disabled` for disabled rows.
- Token `widget.table.focus` for focused active enabled row.
- Token `widget.table.row` otherwise.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_table.py src/loushang/tui/ui_parts/widgets/table.py
git commit -m "feat(tui): add table navigation and activation"
```

---

### Task 5: Add And Implement Theme Regression Coverage

**Files:**
- Modify: `tests/tui/test_widgets_table.py`
- Modify: `src/loushang/tui/ui_parts/widgets/table.py`

- [ ] **Step 1: Add failing theme and width-stability tests**

```python
def test_table_applies_theme_tokens_and_preserves_visible_width() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.table.header": {"color": "cyan"},
            "widget.table.row": {"color": "white"},
            "widget.table.focus": {"bold": True, "color": "green"},
            "widget.table.disabled": {"dim": True},
            "widget.table.empty": {"color": "bright_black"},
        }
    )
    table = Table(
        [TableColumn("name", "Name")],
        [
            TableRow("build", {"name": "Build"}),
            TableRow("skip", {"name": "Skip"}, disabled=True),
        ],
        theme=theme,
    )
    table.focus()

    raw = render_lines(table, width=20, height=3)

    assert raw[0].startswith("\x1b[36m  Name")
    assert raw[1].startswith("\x1b[1;32m> Build")
    assert raw[2].startswith("\x1b[2m  Skip")
    assert plain_lines(table, width=20, height=3) == (
        "  Name",
        "> Build",
        "  Skip",
    )
    assert_widths_within(raw, 20)


def test_table_empty_state_uses_theme_and_width_rules() -> None:
    theme = ThemeResolver(defaults={"widget.table.empty": {"color": "bright_black"}})

    no_columns = Table([], [], empty_text="Nothing here", theme=theme)
    with_columns = Table([TableColumn("name", "Name")], [], empty_text="Nothing here", theme=theme)

    assert render_lines(no_columns, width=8, height=2)[0].startswith("\x1b[90mNothing")
    assert plain_lines(no_columns, width=8, height=2) == ("Nothing",)
    assert plain_lines(with_columns, width=12, height=3) == (
        "  Name",
        "  Nothing",
    )
```

- [ ] **Step 2: Run focused tests to verify failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: FAIL if theme tokens are not applied to each table line type.

- [ ] **Step 3: Apply theme tokens in render helpers**

Ensure helper functions style the entire line after prefix and cells are composed:

```python
def _table_header_line(table: Table, widths: Sequence[int], prefix_width: int, target_width: int) -> str:
    prefix = " " * prefix_width
    cells = _join_cells(tuple(column.header for column in table._columns), widths, table._columns)
    line = truncate_to_width(f"{prefix}{cells}", max_width=target_width, ellipsis="")
    return style_text(line, table.theme, "widget.table.header")
```

Use analogous logic for:

- `_table_body_line(...)`
- `_table_empty_line(...)`

Do not style separators independently.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: PASS.

- [ ] **Step 5: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_table.py src/loushang/tui/ui_parts/widgets/table.py
git commit -m "test(tui): cover table theme rendering"
```

---

### Task 6: Add Docs And Example

**Files:**
- Create: `examples/tui/46_widgets_table.py`
- Modify: `tests/tui/test_widgets_table.py`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`

- [ ] **Step 1: Add failing example import test**

Append:

```python
def test_widgets_table_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/46_widgets_table.py", run_name="__test__")

    assert "build_app" in namespace
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py::test_widgets_table_example_imports -q
```

Expected: FAIL because `examples/tui/46_widgets_table.py` does not exist.

- [ ] **Step 3: Create `examples/tui/46_widgets_table.py`**

Use a compact app modeled after `45_widgets_light_controls.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    Table,
    TableColumn,
    TableRow,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class TableApp(FocusableMixin):
    table: Table = field(default_factory=lambda: Table(_columns(), _rows()))
    message: str = "Select a job"

    def __post_init__(self) -> None:
        super().__init__()
        self.table.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [
            RenderLine(truncate_to_width("Table", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            *self.table.render(RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 4))).lines,
            RenderLine(""),
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        result = self.table.handle_input(event)
        if isinstance(result, str):
            self.message = f"Selected {result}"
            return True
        return result


def build_app() -> Tui:
    tui = Tui()
    app = TableApp()
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


def _columns() -> list[TableColumn]:
    return [
        TableColumn("job", "Job", width=12),
        TableColumn("status", "Status"),
        TableColumn("runs", "Runs", width=5, align="right"),
    ]


def _rows() -> list[TableRow]:
    return [
        TableRow("build", {"job": "Build", "status": "ready", "runs": 12}),
        TableRow("deploy", {"job": "Deploy", "status": "blocked", "runs": 3}),
        TableRow("archive", {"job": "Archive", "status": "disabled", "runs": 0}, disabled=True),
    ]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 4: Update English reference docs**

In `docs/en/reference/tui-widgets.md`:

- Add a `## P1A Data Controls` section after P0C.
- Add table row:

```markdown
| `Table` / `TableColumn` / `TableRow` | Dense row/column data with local active-row navigation. |
```

- Add a short usage snippet:

```python
from loushang.tui import Table, TableColumn, TableRow

table = Table(
    [TableColumn("job", "Job"), TableColumn("status", "Status")],
    [TableRow("build", {"job": "Build", "status": "ready"})],
)
table.focus()
```

- Add theme tokens:

```markdown
| `widget.table.header` | Table header rows. |
| `widget.table.row` | Enabled inactive table rows. |
| `widget.table.focus` | Focused active table row. |
| `widget.table.disabled` | Disabled table rows. |
| `widget.table.empty` | Table empty-state text. |
```

- Add example link:

```markdown
- [examples/tui/46_widgets_table.py](../../../examples/tui/46_widgets_table.py):
  dense table composition with keyboard row selection.
```

- Remove `Table` from the existing `Planned Catalog` sentence because it is no
  longer only planned after this slice.

- [ ] **Step 5: Update Chinese reference docs**

Mirror the same content in `docs/zh-CN/reference/tui-widgets.md`. Keep terminology consistent with the existing page; do not rewrite unrelated sections.
Also remove `Table` from the Chinese planned-catalog list.

- [ ] **Step 6: Run focused tests and Ruff**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
uv --cache-dir .uv-cache run --extra dev ruff check examples/tui/46_widgets_table.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md tests/tui/test_widgets_table.py
```

Expected: PASS and `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add examples/tui/46_widgets_table.py tests/tui/test_widgets_table.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md
git commit -m "docs(tui): document table widget"
```

---

### Task 7: Full Verification And Branch Completion

**Files:**
- No planned edits.

- [ ] **Step 1: Run focused table tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the full TUI suite**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 4: Run Ruff on TUI, docs, and example**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/46_widgets_table.py docs
```

Expected: `All checks passed!`

- [ ] **Step 5: Inspect final branch state**

Run:

```bash
git status --short --branch
git log --oneline main..HEAD
```

Expected:

- Clean worktree.
- Commits include the spec, plan, focused tests/implementation, docs, and example.

- [ ] **Step 6: Invoke completion workflow**

Use `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`.

Present the standard four options:

```text
Implementation complete. What would you like to do?

1. Merge back to main locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```
