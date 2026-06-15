# TUI DataGrid V1 Design

## Status

Draft for spec review.

This is a TUI-lane design for a reusable interactive grid widget. The spec is
temporary in `docs/superpowers/specs`. After implementation, the durable widget
contract should be summarized under
`docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md`.

## Context

`loushang.tui` already has a compact `Table` widget. `Table` is intentionally
row-oriented: it renders dense tabular data, moves focus by row, skips disabled
rows, and activates the current row. That shape works for queues, short status
lists, and summaries.

Several upcoming TUI pages need more than `Table`:

- model lists with sortable columns and editable preferences
- usage, token, latency, cost, benchmark, and diagnostic grids
- stock-like numeric lists with price, delta, percent, and compact volume
- file/search result tables with fixed identity columns and horizontally
  scrollable detail columns
- task or job tables that need multi-select actions

Textual's `DataTable` is useful prior art: it supports adding rows/columns,
row/cell/column cursors, selection messages, fixed rows/columns, zebra stripes,
sorting, and mutable cell operations. `loushang.tui` should not copy Textual's
retained widget model, but it should match the common interaction expectations.

## Problem

Without a reusable `DataGrid`, product pages will either overload `Table` or
hand-roll advanced table behavior repeatedly:

- cell focus and column focus
- horizontal viewport management
- fixed columns
- multi-select state
- editable cells
- sort and mutation APIs
- numeric and percent formatting
- semantic row/cell coloring
- large bounded data rendering

Those behaviors belong in a generic TUI widget. Product pages should own data
loading, domain actions, persistence, and command footers, while `DataGrid`
owns grid navigation, rendering, editing state, and structured intents.

## Goals

- Add a public `DataGrid` widget for interactive tabular data.
- Keep `Table` unchanged as the smaller row-focused widget.
- Support cursor modes: `row`, `cell`, `column`, and `none`.
- Support keyboard navigation across rows and columns.
- Support vertical and horizontal viewport windowing.
- Support left fixed columns.
- Support optional row labels and header rendering.
- Support disabled rows and disabled cells that remain visible but are skipped.
- Support single and multi selection without mouse dependency.
- Support simple inline text editing with column-level parse and validation.
- Support mutable APIs for adding, removing, clearing, and updating data.
- Support explicit sorting while preserving active row/selection by key.
- Support column-level text, number, percent, delta, and compact-number
  formatting.
- Support semantic row/cell theme tokens for positive/negative/neutral values
  and other product states.
- Render only the visible row and column windows.
- Cover 10k-row viewport behavior in tests without making 100k rows a blocking
  V1 performance claim.
- Export the stable public API from `loushang.tui.ui_parts.widgets`,
  `loushang.tui.ui_parts`, and top-level `loushang.tui`.
- Add focused tests, internal docs, and a rich generic example.

## Non-Goals

- Do not add mouse hover, click, drag, or pointer selection in V1.
- Do not add variable row height.
- Do not support Rich renderable cells. Cell formatters return text.
- Do not add drag-to-resize or mouse-driven column resizing.
- Do not add spreadsheet formulas.
- Do not add async data loading or background workers.
- Do not add a global data model, database adapter, or virtual data provider.
- Do not add copy/paste range import or export.
- Do not make `DataGrid` a stock-list-specific widget.
- Do not migrate existing product pages in this slice.

## Package Scope

Generic reusable TUI code:

- `src/loushang/tui/ui_parts/widgets/data_grid.py`
- public exports from:
  - `src/loushang/tui/ui_parts/widgets/__init__.py`
  - `src/loushang/tui/ui_parts/__init__.py`
  - `src/loushang/tui/__init__.py`

Tests:

- `tests/tui/test_widgets_data_grid.py`
- existing public export/import-boundary tests where applicable

Example:

- `examples/tui/58_widgets_datagrid.py`

Long-term internal documentation after implementation:

- `docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md`
- update `docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`

## Relationship To Table

`Table` remains the recommended widget when the active unit is a row and the
data is compact. `DataGrid` is for advanced interactions:

| Capability | Table | DataGrid |
| --- | --- | --- |
| row focus | yes | yes |
| cell focus | no | yes |
| column focus | no | yes |
| horizontal viewport | no | yes |
| fixed columns | no | yes |
| sorting | no | yes |
| mutable rows/cells | no | yes |
| multi-select | no | yes |
| inline editing | no | yes |
| numeric formatters | no | yes |

Do not retrofit `Table` into `DataGrid`. Some width and alignment helpers may be
shared later if duplication becomes meaningful, but V1 should prefer a clear
new contract over premature coupling.

## Public API

First version:

```python
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

DataGridAlign = Literal["left", "right", "center"]
DataGridCursorMode = Literal["row", "cell", "column", "none"]
DataGridSelectionMode = Literal["none", "single", "multi"]
DataGridSortDirection = Literal["asc", "desc"]

DataGridCellKey = tuple[str, str]  # row_key, column_key

@dataclass(frozen=True, slots=True)
class DataGridFormatResult:
    text: str
    theme_token: str | None = None

DataGridFormatter = Callable[[object], str | DataGridFormatResult]
DataGridParser = Callable[[str], object]
DataGridValidator = Callable[[object], str | None]
DataGridThemeResolver = Callable[[object], str | None]

@dataclass(frozen=True, slots=True)
class DataGridColumn:
    key: str
    header: str
    width: int | None = None
    min_width: int = 1
    max_width: int | None = None
    align: DataGridAlign = "left"
    editable: bool = False
    sortable: bool = True
    hidden: bool = False
    formatter: DataGridFormatter | None = None
    parser: DataGridParser | None = None
    validator: DataGridValidator | None = None
    theme_token: str | None = None
    theme_token_for_value: DataGridThemeResolver | None = None

@dataclass(frozen=True, slots=True)
class DataGridCell:
    value: object
    disabled: bool = False
    editable: bool | None = None
    theme_token: str | None = None

@dataclass(frozen=True, slots=True)
class DataGridRow:
    key: str
    cells: Mapping[str, object | DataGridCell] | Sequence[object | DataGridCell]
    label: str | None = None
    disabled: bool = False
    theme_token: str | None = None
    on_select: Callable[[], object] | None = None

@dataclass(frozen=True, slots=True)
class DataGridSelect:
    row_key: str | None
    column_key: str | None
    value: object | None
    cursor_mode: DataGridCursorMode

@dataclass(frozen=True, slots=True)
class DataGridSelectionChange:
    selected_rows: frozenset[str]
    selected_cells: frozenset[DataGridCellKey]

@dataclass(frozen=True, slots=True)
class DataGridEdit:
    row_key: str
    column_key: str
    old_value: object | None
    new_value: object

@dataclass(slots=True)
class DataGrid:
    columns: Sequence[DataGridColumn]
    rows: Sequence[DataGridRow | Mapping[str, object] | Sequence[object]]
    active_row_key: str | None = None
    active_column_key: str | None = None
    cursor_mode: DataGridCursorMode = "row"
    selection_mode: DataGridSelectionMode = "single"
    show_header: bool = True
    show_row_labels: bool = False
    fixed_columns: int = 0
    zebra_stripes: bool = False
    empty_text: str = "No rows"
    wrap_rows: bool = True
    wrap_columns: bool = False
    theme: ThemeResolver | None = None
    focused: bool = False
```

`DataGrid` normalizes columns and rows during construction and after mutation.
Duplicate column keys or row keys raise `ValueError`. Hidden columns stay in
the data model but do not participate in render or navigation.

## Formatter API

Formatters convert raw values to display text and optional semantic theme
tokens. They must not mutate grid state.

Built-in V1 formatter classes:

```python
@dataclass(frozen=True, slots=True)
class TextFormatter:
    none_text: str = ""

@dataclass(frozen=True, slots=True)
class NumberFormatter:
    precision: int | None = None
    thousands: bool = False
    sign: bool = False
    none_text: str = ""
    invalid_text: str = ""

@dataclass(frozen=True, slots=True)
class PercentFormatter:
    precision: int = 2
    scale: float = 100.0
    sign: bool = False
    none_text: str = ""
    invalid_text: str = ""

@dataclass(frozen=True, slots=True)
class DeltaFormatter:
    precision: int = 2
    sign: bool = True
    zero_sign: bool = False
    none_text: str = ""
    invalid_text: str = ""

@dataclass(frozen=True, slots=True)
class CompactNumberFormatter:
    precision: int = 1
    sign: bool = False
    none_text: str = ""
    invalid_text: str = ""
```

Numeric formatters should accept `int`, `float`, and `Decimal`. `None`,
`NaN`, and infinity render as configured fallback text. The fallback default is
empty string, not a Unicode dash, to keep the widget ASCII by default. Product
examples may choose a visible fallback when useful.

Stock-like grids are expressed through generic columns:

```python
DataGridColumn(
    key="change_pct",
    header="Change %",
    align="right",
    width=9,
    formatter=PercentFormatter(precision=2, sign=True),
    theme_token_for_value=lambda value: (
        "widget.dataGrid.positive"
        if value > 0
        else "widget.dataGrid.negative"
        if value < 0
        else "widget.dataGrid.neutral"
    ),
)
```

This supports price, delta, percent, volume, market cap, latency, token counts,
cost, and duration columns without making the grid domain-specific.

## Rendering Model

Rendering order:

1. optional header row
2. visible body rows
3. one empty row when there are columns but no rows

Every rendered line must fit `constraints.width` and `constraints.max_height`.
The effective width is `autowrap_safe_width(constraints.width)`.

Row prefix:

- focused active row in row/cell mode uses `"> "`
- inactive rows use `"  "`
- header reserves the same prefix width
- when width is too narrow, prefixes truncate rather than overflowing

Row labels:

- when `show_row_labels=True`, labels render after the row prefix and before
  data columns
- labels are not part of `fixed_columns`
- label width is derived from visible labels and constrained by available width
- labels are navigable only through row focus, not as editable cells

Column layout:

- hidden columns are excluded
- left fixed columns render first
- scrollable columns render after fixed columns
- fixed columns keep their relative order
- horizontal navigation ensures the active column is visible in the scrollable
  viewport
- if fixed columns consume all available width, scrollable columns may be
  fully hidden, but row navigation still works

Width allocation:

- fixed `width` values are honored when possible
- flexible columns start at `min_width`
- `max_width` caps flexible expansion
- remaining width is distributed left to right across flexible visible columns
- if minimum width exceeds available width, shrink from right to left within
  the scrollable window before shrinking fixed columns
- cells assigned zero width are omitted
- all truncation uses visible cell width, not raw string length

Alignment:

- `left` pads on the right
- `right` pads on the left
- `center` splits padding, with extra padding on the right

Zebra stripes:

- when `zebra_stripes=True`, odd visible body rows receive
  `widget.dataGrid.rowAlternate` before any row/cell semantic token
- zebra styling never applies to header or empty rows

Cursor declaration:

- focused row mode declares cursor at the active row prefix
- focused cell mode declares cursor at the active cell start when visible
- focused column mode declares cursor at the active header cell start when
  header is visible; otherwise it declares no cursor
- cursor mode `none` declares no cursor

## Input Behavior

Focus:

- `focus()` sets `focused=True`
- `blur()` sets `focused=False` and cancels active edit state

Navigation keys:

| Input | Row mode | Cell mode | Column mode |
| --- | --- | --- | --- |
| `up` | previous enabled row | previous enabled row | no-op boundary result |
| `down` | next enabled row | next enabled row | no-op boundary result |
| `left` | no-op boundary result | previous enabled cell/column | previous enabled column |
| `right` | no-op boundary result | next enabled cell/column | next enabled column |
| `home` | first enabled row | first enabled cell in row | first enabled column |
| `end` | last enabled row | last enabled cell in row | last enabled column |
| `pageup` | previous page of rows | previous page of rows | no-op boundary result |
| `pagedown` | next page of rows | next page of rows | no-op boundary result |

Return values:

- `True` when active cursor or selection changed
- `False` when input was understood but cursor did not move because of a
  boundary or disabled target
- `None` when there is no enabled target or the input is not consumed

Wrapping:

- `wrap_rows=True` wraps up/down between first and last enabled rows
- `wrap_columns=True` wraps left/right between first and last enabled columns
- page movement never wraps

Activation:

- `enter` activates the current row/cell/column unless editing is active
- printable text `" "` or key `"space"` toggles selection when selection is
  enabled; otherwise it activates
- activation returns `DataGridSelect` unless the row has `on_select`, in which
  case it returns `callback_result(row.on_select())`
- disabled rows and disabled cells do not activate

## Selection

Selection mode controls persistent selection, separate from the active cursor.

`selection_mode="none"`:

- no persistent selection
- Space behaves like activation
- `selected_rows` and `selected_cells` are empty

`selection_mode="single"`:

- selecting a row or cell replaces the previous selection
- row cursor mode selects rows
- cell cursor mode selects cells
- column cursor mode selects all enabled cells in the column as a single user
  action, represented as cell selection

`selection_mode="multi"`:

- Space toggles the active row/cell/column selection
- `a` with control modifier may be supported later by the input router, but V1
  should expose `select_all()` as an API rather than depend on a platform key
- `clear_selection()` clears all selected rows and cells

Required public selection properties and methods:

- `selected_row_keys: frozenset[str]`
- `selected_cell_keys: frozenset[DataGridCellKey]`
- `select_row(row_key: str) -> bool`
- `toggle_row(row_key: str) -> bool`
- `select_cell(row_key: str, column_key: str) -> bool`
- `toggle_cell(row_key: str, column_key: str) -> bool`
- `select_all() -> bool`
- `clear_selection() -> bool`

The grid may return `DataGridSelectionChange` from explicit selection inputs.
Programmatic selection methods return bool for mutation success.

## Inline Editing

Editing is intentionally simple text editing, not a full nested editor.

Editing entry:

- `e` starts editing the active editable cell in cell mode
- `enter` starts editing an editable cell when `activate_edits=True` is added
  in a future slice; V1 should keep Enter as activation to avoid ambiguity
- programmatic `start_edit(row_key, column_key) -> bool`

Editing state:

- V1 keeps a single editing buffer string
- while editing, printable text appends to the buffer
- `backspace` removes one cell-width-safe character from the buffer
- `left` and `right` within the buffer are out of scope for V1
- editing render shows the buffer in the active cell with
  `widget.dataGrid.editing`

Commit/cancel:

- `enter` commits
- `esc` cancels
- `commit_edit() -> DataGridEdit | None`
- `cancel_edit() -> bool`

Validation:

- a cell is editable when the column is editable and the row/cell are enabled
- `DataGridCell.editable` overrides column editability when not `None`
- parser receives the buffer string and returns the new raw value
- parser exceptions become validation errors; they do not crash render
- validator returns `None` for valid or a message string for invalid
- invalid commit leaves editing active and exposes
  `editing_error: str | None`
- successful commit updates the cell value and returns `DataGridEdit`

Editing is disabled in row and column cursor modes unless the caller starts an
edit programmatically for a specific cell.

## Sorting

Sorting is explicit and never occurs during render.

Required API:

- `sort_by(column_key: str, reverse: bool = False) -> bool`
- `clear_sort() -> bool`
- `sort_state: tuple[str, DataGridSortDirection] | None`

Rules:

- sorting a hidden or unknown column raises `ValueError`
- sorting a `sortable=False` column returns `False`
- sort keys use the raw cell value by default
- `None` sorts after real values in ascending order
- sort is stable
- active row, selected rows, and selected cells are preserved by row/cell key
- if the active row no longer exists after mutation, active state repairs to
  the nearest enabled visible row

Custom sort functions are out of scope for the first implementation. If needed,
they can be added to `DataGridColumn` later without changing the V1
interaction model.

## Mutation API

Required methods:

- `add_row(row: DataGridRow | Mapping[str, object] | Sequence[object], *, index: int | None = None) -> str`
- `remove_row(row_key: str) -> bool`
- `add_column(column: DataGridColumn, *, index: int | None = None, default: object = "") -> bool`
- `remove_column(column_key: str) -> bool`
- `update_cell(row_key: str, column_key: str, value: object | DataGridCell) -> bool`
- `clear() -> None`

Mutation rules:

- row and column keys must remain unique
- removing active row/column repairs active state
- removing selected rows/cells removes them from selection sets
- adding rows while a sort is active does not auto-sort; caller can call
  `sort_by()` again
- mutation during editing cancels editing unless the mutation is the successful
  edit commit for the active cell

## Large Data Contract

V1 should be efficient by design without promising a fully virtualized data
engine.

Required behavior:

- render only formats visible body rows and visible columns
- hidden/offscreen cells are not formatted during render
- viewport repair uses row keys and visible indices, not raw object identity
- selection uses row/cell keys
- sorting is explicit and may be O(n log n)
- tests include 10k rows to prove viewport behavior does not render or format
  the whole dataset

Non-binding target:

- 100k rows should remain architecturally possible, but V1 does not need a
  benchmark gate or external data provider API.

## Theme Tokens

Base tokens:

| Token | Applies to |
| --- | --- |
| `widget.dataGrid.header` | Header row |
| `widget.dataGrid.row` | Normal body rows |
| `widget.dataGrid.rowAlternate` | Odd visible body rows when zebra is enabled |
| `widget.dataGrid.focusRow` | Active row while focused in row or cell mode |
| `widget.dataGrid.focusCell` | Active cell while focused in cell mode |
| `widget.dataGrid.focusColumn` | Active column/header while focused in column mode |
| `widget.dataGrid.selectedRow` | Selected row |
| `widget.dataGrid.selectedCell` | Selected cell |
| `widget.dataGrid.disabled` | Disabled rows and cells |
| `widget.dataGrid.empty` | Empty row |
| `widget.dataGrid.fixedColumn` | Fixed columns |
| `widget.dataGrid.editing` | Editing cell |
| `widget.dataGrid.editError` | Editing validation error text |

Semantic value tokens:

| Token | Applies to |
| --- | --- |
| `widget.dataGrid.positive` | Positive numeric values |
| `widget.dataGrid.negative` | Negative numeric values |
| `widget.dataGrid.neutral` | Zero/neutral numeric values |
| `widget.dataGrid.warning` | Warning state cells or rows |
| `widget.dataGrid.error` | Error state cells or rows |

Composition order should make focus visible:

1. base row/header token
2. zebra token
3. fixed column token
4. row theme token
5. column theme token
6. formatted value or cell theme token
7. selected token
8. focus token
9. editing or edit-error token

Later tokens override earlier tokens.

## Example

Create `examples/tui/58_widgets_datagrid.py`.

The example should demonstrate:

- a stock-like watchlist, but named generically enough to show the widget is
  not stock-specific
- columns: symbol, price, change, change percent, volume, status
- right-aligned numeric columns
- percent and compact-number formatters
- positive/negative/neutral theme tokens
- row and cell cursor mode toggling
- multi-select with Space
- simple editing for a notes/status column
- sorting by price or percent change
- fixed symbol column
- enough rows to show vertical and horizontal viewport behavior
- footer text with key hints

The example should not draw sparklines or price charts.

## Testing Obligations

Add focused tests for:

- public re-exports
- duplicate row/column key validation
- mapping, sequence, and `DataGridRow` normalization
- hidden columns excluded from render/navigation
- row cursor navigation, wrapping, disabled-row skipping, home/end/page keys
- cell cursor navigation, wrapping, disabled-cell skipping
- column cursor navigation and header cursor declaration
- vertical viewport keeps active row visible
- horizontal viewport keeps active column visible
- fixed columns remain visible while scrolling columns
- row labels render and do not become editable cells
- header hidden and empty-state rendering
- zebra stripe theme application
- selected row/cell rendering and selection APIs
- multi-select toggle and clear behavior
- activation returns `DataGridSelect`
- row `on_select` callback behavior
- inline edit start, buffer input, commit, cancel, parser failure, validation
  failure, and successful mutation
- sort state, stable sort, disabled/hidden/unsortable handling, active/selection
  preservation after sort
- add/remove/update/clear mutation and active/selection repair
- built-in text, number, percent, delta, and compact-number formatters
- formatter fallback for `None`, `NaN`, and infinity
- semantic positive/negative/neutral theme tokens
- 10k-row viewport behavior formats only visible rows/cells
- example import and playback
- documentation reference tests where applicable

## Implementation Notes

Implementation should keep the code split into small private helpers:

- data normalization
- visible row/column calculation
- width allocation
- cell formatting
- navigation repair
- selection mutation
- edit state handling
- rendering

If `data_grid.py` grows too large during implementation, split helpers into
private sibling modules only when it materially improves readability. Avoid
creating a public subpackage for V1.

Use existing utilities where they fit:

- `autowrap_safe_width`
- `truncate_to_width`
- `visible_width`
- `style_text`
- `callback_result`
- `is_activation_event`

## Open Decisions For Review

1. Should Enter start editing editable cells in V1, or should editing require
   `e` so Enter remains activation everywhere?
2. Should column cursor mode selection select all enabled cells in the column,
   or should it only return a `DataGridSelect` for the column header?
3. Should formatter invalid numeric values default to empty text or a visible
   placeholder in the built-in examples?
4. Should `selection_mode="single"` default to selecting rows in row mode and
   cells in cell mode, or should it remain activation-only until Space is
   pressed?
