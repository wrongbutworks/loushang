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

## V1 Decisions

These decisions are fixed for implementation planning:

- Enter activates the current target by default. Editable columns may opt in to
  `enter_behavior="edit"` so Enter starts editing that column in cell mode.
  Editing can also start with `e` or through `start_edit(row_key, column_key)`.
- Space is the only default keyboard selection action. Cursor movement never
  implicitly changes persistent selection.
- Column cursor selection selects all enabled cells in the active visible
  column only when `selection_mode="multi"`. Disabled rows and disabled cells
  are skipped.
- Built-in formatter invalid values default to empty text. Examples may choose
  explicit ASCII placeholders such as `N/A`.
- Constructor shorthand rows get deterministic generated keys. Callers that
  need long-lived semantic keys should pass `DataGridRow`.
- Data-entry flows are supported without making the grid domain-specific:
  callers can add a row, focus an editable code column, commit edits, update
  dependent cells such as name, advance to quantity, and handle later
  activation in product code.
- `cursor_mode="none"` is display-only for input handling: no navigation,
  activation, selection, or editing input is consumed.

## Public API

First version:

```python
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from loushang.tui.theme import ThemeResolver

DataGridAlign = Literal["left", "right", "center"]
DataGridCursorMode = Literal["row", "cell", "column", "none"]
DataGridSelectionMode = Literal["none", "single", "multi"]
DataGridEnterBehavior = Literal["activate", "edit"]
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
    enter_behavior: DataGridEnterBehavior = "activate"
    edit_next_column_key: str | None = None
    edit_accepts_unchanged: bool = True
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
    pinned: Literal["top", "bottom"] | None = None
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

`DataGrid.handle_input(event) -> object` follows the existing widget pattern:
navigation returns booleans or `None`, activation returns structured selection
objects or callback results, selection returns `DataGridSelectionChange` when
state changes, and editing returns edit-specific results described below.

`DataGrid` normalizes columns and rows during construction and after mutation.
Duplicate column keys or row keys raise `ValueError`. Hidden columns stay in
the data model but do not participate in render or navigation.

Row key normalization:

- `DataGridRow.key` is used as-is after `str()` conversion.
- Mapping and sequence rows receive generated keys of the form `row-<n>`, where
  `n` is the row's construction-order index.
- `add_row()` for a mapping or sequence row uses the next monotonically
  increasing generated key and returns it.
- Generated keys are never reused after row removal during the lifetime of the
  grid.
- If a generated key would collide with an explicit `DataGridRow.key`, the grid
  advances the generated counter until it finds an unused key.
- Mixed explicit and shorthand rows are allowed, but explicit `DataGridRow`
  should be used for durable product state, persisted selection, or callbacks.

Cell normalization:

- Mapping rows resolve cells by column key.
- Sequence rows resolve cells by visible and hidden column order.
- Missing mapping keys and short sequences produce empty string cell values.
- `DataGridCell` preserves its metadata. Plain cell values are wrapped as
  enabled, column-default-editability cells.
- Hidden columns still receive normalized cell values so they can later be
  shown or updated.

Pinned rows:

- `DataGridRow.pinned=None` is a normal scrollable data row.
- `pinned="top"` renders before the scrollable body.
- `pinned="bottom"` renders after the scrollable body.
- pinned rows are intended for summaries, totals, section headers, or other
  derived rows.
- pinned rows default to non-interactive behavior: they are skipped by
  navigation, selection, sorting, editing, and activation unless a future slice
  adds explicit opt-in interactivity.
- pinned rows still use normal cells, formatters, and theme tokens.

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

Concrete built-in formatter rules:

- Numeric conversion uses `Decimal(str(value))` for `int`, `float`, and
  `Decimal` inputs.
- `None` renders `none_text`.
- conversion failure, `NaN`, and infinity render `invalid_text`.
- `NumberFormatter(precision=None)` renders the normalized decimal without
  forced fractional digits.
- `NumberFormatter(precision=n)` renders exactly `n` fractional digits using
  half-up rounding.
- `thousands=True` adds comma grouping to the integer part.
- `sign=True` prefixes positive values with `+`; zero has no sign.
- `PercentFormatter` multiplies the numeric value by `scale`, formats with
  exactly `precision` fractional digits, then appends `%`.
- `DeltaFormatter` follows `NumberFormatter` with `sign=True` by default.
  `zero_sign=True` renders zero with `+`.
- `CompactNumberFormatter` uses suffixes `K`, `M`, `B`, and `T` at thresholds
  `1_000`, `1_000_000`, `1_000_000_000`, and `1_000_000_000_000`. Values below
  `1_000` render as normal numbers with at most `precision` fractional digits.
- Compact formatting preserves the sign before the compacted number.

Example outputs:

| Formatter | Input | Output |
| --- | --- | --- |
| `NumberFormatter(precision=2)` | `1234.5` | `1234.50` |
| `NumberFormatter(precision=2, thousands=True)` | `1234.5` | `1,234.50` |
| `PercentFormatter(precision=2, sign=True)` | `0.0345` | `+3.45%` |
| `DeltaFormatter(precision=2)` | `-1.2` | `-1.20` |
| `CompactNumberFormatter(precision=1)` | `1250000` | `1.3M` |

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
2. pinned top rows
3. visible scrollable body rows
4. pinned bottom rows
5. one empty row when there are columns but no rows

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
- zebra styling never applies to header, pinned rows, or empty rows

Cursor declaration:

- focused row mode declares cursor at the active row prefix
- focused cell mode declares cursor at the active cell start when visible
- focused column mode declares cursor at the active header cell start when
  header is visible; otherwise it declares no cursor
- cursor mode `none` declares no cursor

## Active State And Repair

Active state is stored by keys, not indexes.

Enabled targets:

- an enabled row is a non-disabled row
- an enabled cell is a cell in an enabled row, visible non-hidden column, and
  non-disabled cell
- an enabled column is a visible non-hidden column

Initial repair:

- `active_row_key` is accepted when it names an enabled row. Otherwise the grid
  chooses the first enabled row, or `None` when no enabled row exists.
- `active_column_key` is accepted when it names a visible non-hidden column.
  Otherwise the grid chooses the first visible non-hidden column, or `None`
  when no visible column exists.
- in cell mode, if the active row/column pair is not an enabled cell, the grid
  chooses the first enabled cell in row-major order.
- in row mode, `active_column_key` may still be repaired for future mode
  changes, but activation and cursor declaration use only `active_row_key`.
- in column mode, `active_row_key` may remain repaired for future mode changes,
  but activation and cursor declaration use only `active_column_key`.
- in `cursor_mode="none"`, active keys are repaired for public state
  consistency but no cursor is rendered and no input is consumed.

Mutation repair:

- removing the active row repairs to the nearest enabled row after the removed
  row's previous position, then before it, then `None`
- removing the active column repairs to the nearest visible column after the
  removed column's previous position, then before it, then `None`
- disabling an active row or cell triggers the same repair as removal
- hiding an active column triggers the same repair as removal
- if no enabled cell exists in cell mode, both active row and column remain as
  best-effort repaired keys, but cell navigation, activation, selection, and
  editing return `None`

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

- navigation returns `True` when the active cursor changed
- `False` when input was understood but cursor did not move because of a
  boundary or disabled target
- `None` when there is no enabled target or the input is not consumed

Wrapping:

- `wrap_rows=True` wraps up/down between first and last enabled rows
- `wrap_columns=True` wraps left/right between first and last enabled columns
- page movement never wraps

Activation:

- `enter` activates the current row/cell/column unless editing is active or the
  active cell's column has `enter_behavior="edit"`
- printable text `" "` or key `"space"` toggles selection when selection is
  enabled; otherwise it activates
- row-mode activation returns `callback_result(row.on_select())` when the row
  has `on_select`; cell and column activation always return `DataGridSelect`
- disabled rows and disabled cells do not activate
- in row mode, activation returns
  `DataGridSelect(row_key=<active row>, column_key=None, value=None,
  cursor_mode="row")`
- in cell mode, activation returns
  `DataGridSelect(row_key=<active row>, column_key=<active column>,
  value=<raw cell value>, cursor_mode="cell")`
- in column mode, activation returns
  `DataGridSelect(row_key=None, column_key=<active column>, value=None,
  cursor_mode="column")`
- in `cursor_mode="none"`, input activation returns `None`

Enter-to-edit rule:

- applies only in cell mode
- requires an active enabled editable cell
- requires the active column to set `enter_behavior="edit"`
- returns the same result as `start_edit(row_key, column_key)`
- editing state still uses Enter for commit once editing has started

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
- column cursor mode does not persist selection because V1 has no
  selected-column state and single mode cannot select multiple cells

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

The grid returns `DataGridSelectionChange` from explicit selection inputs when
selection changes. Programmatic selection methods return bool for mutation
success.

Selection input return rules:

- Space returns `DataGridSelectionChange` when selection changed.
- Space returns `False` when the target is already selected in single-selection
  mode.
- Space returns `False` in `selection_mode="single"` with
  `cursor_mode="column"` because V1 has no selected-column state.
- Space returns `None` when there is no selectable target or
  `selection_mode="none"` and activation also has no target.
- `selection_mode="none"` never stores selection and Space follows activation
  return rules.

Selection target rules:

- row mode targets the active enabled row
- cell mode targets the active enabled cell
- column mode targets all enabled cells in the active visible column
- hidden columns are never selected by `select_all()` or column selection
- disabled rows and disabled cells are never selected
- `selection_mode="single"` never selects multiple targets; programmatic
  `select_all()` returns `False`
- `selection_mode="multi"` enables `select_all()`
- `select_all()` in multi-selection row cursor mode selects all enabled rows
- `select_all()` in multi-selection cell cursor mode selects all enabled cells
  in visible columns
- `select_all()` in multi-selection column cursor mode selects all enabled
  cells in the active visible column
- `select_all()` returns `False` when `selection_mode="none"` or
  `cursor_mode="none"`

## Inline Editing

Editing is intentionally simple text editing, not a full nested editor.

Editing entry:

- `e` starts editing the active editable cell in cell mode
- `enter` starts editing only when the active editable cell's column has
  `enter_behavior="edit"`
- programmatic `start_edit(row_key, column_key) -> bool`

Editing state:

- V1 keeps a single editing buffer string
- the buffer initializes to `""` for `None`, otherwise `str(raw_value)`;
  default cell values therefore appear in the edit buffer
- formatting is not used to initialize the edit buffer
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

Editing input return rules:

- `e` returns `True` when it starts editing
- `e` returns `False` when cell mode has an active cell but that cell is not
  editable
- `e` returns `None` outside cell mode
- printable text while editing returns `True`
- `backspace` while editing returns `True` when the buffer changed and `False`
  when the buffer was already empty
- `enter` while editing returns `DataGridEdit` on successful commit and
  `False` on parser or validation failure
- `esc` while editing returns `True` when it cancels an edit

Validation:

- a cell is editable when the column is editable and the row/cell are enabled
- `DataGridCell.editable` overrides column editability when not `None`
- parser receives the buffer string and returns the new raw value
- when no parser is configured, the committed raw value is the buffer string
- parser exceptions become validation errors; they do not crash render
- validator returns `None` for valid or a message string for invalid
- parser exception text is used as `editing_error`, falling back to
  `"Invalid value"` when the exception has no message
- invalid commit leaves editing active and exposes
  `editing_error: str | None`
- when the user presses Enter without changing a prefilled buffer,
  `edit_accepts_unchanged=True` commits the existing raw value and continues
  the edit flow
- when `edit_accepts_unchanged=False`, unchanged commit returns `False` and
  leaves editing active
- successful commit updates the cell value and returns `DataGridEdit`
- successful commit preserves existing `DataGridCell` metadata while replacing
  only its `value`
- when the committed column has `edit_next_column_key`, successful commit moves
  the active cell to that column in the same row after updating the value
- if the next column is editable and the next cell is enabled, the grid starts
  editing the next cell immediately, regardless of that next column's
  `enter_behavior`
- if the next column is missing, hidden, disabled, or not editable, the grid
  repairs active state but does not start another edit
- if the next cell has a default value, its edit buffer starts with that value;
  pressing Enter immediately accepts the default when
  `edit_accepts_unchanged=True`

Editing is disabled in row and column cursor modes unless the caller starts an
edit programmatically for a specific cell.

## Data Entry Workflow

`DataGrid` should support fast keyboard entry workflows without embedding
business logic. A product page should be able to implement this pattern:

1. Add a blank row.
2. Focus the `code` cell and start editing immediately.
3. User types a code and presses Enter.
4. Grid commits the code and returns `DataGridEdit`.
5. Product code handles the edit result, looks up data synchronously or
   asynchronously, and calls `update_cell()` for dependent cells such as name,
   price, unit, or tax rate.
6. Grid advances to the configured `quantity` cell and starts editing it. The
   quantity cell may already contain a default value such as `1`.
7. User either presses Enter to accept the default quantity or types a new
   quantity and presses Enter.
8. Grid commits quantity and returns `DataGridEdit`.
9. The next Enter activates the row or cell, returning `DataGridSelect`; product
   code can trigger backend processing.
10. Product code can append the next blank row, update pinned total rows, and
   start editing the new row's `code` cell.

The generic widget owns focus, edit buffer, commit, and next-cell movement. It
does not own code lookup, backend actions, inventory rules, or row factories.
`edit_next_column_key` may point to any visible editable column in the same row;
it is not limited to adjacent columns, so products can skip display-only
columns such as `name`.

Product-side dependent updates:

- after a `DataGridEdit`, product code may update any other cells in the same
  row with `update_cell()`
- those updates may happen synchronously before the next render or
  asynchronously after backend lookup returns
- updating non-active cells must not cancel the current edit-next flow
- updating the active editing cell cancels the edit unless it is the successful
  commit for that same cell
- product code may recompute summary values and update a pinned bottom row
  after each edit or activation

Append-after-submit pattern:

- the grid does not automatically create rows after a final column; product
  code owns that decision
- after final-cell edit or row/cell activation, product code may call
  `add_row(..., activate=True, edit_column_key="code")`
- summary or total rows should be represented as `DataGridRow(pinned="bottom",
  disabled=True, ...)` and updated by product code
- pinned total rows are excluded from `select_all()`, sorting, editing, and
  normal navigation

Column configuration for this pattern:

```python
DataGridColumn(
    key="code",
    header="Code",
    editable=True,
    enter_behavior="edit",
    edit_next_column_key="quantity",
)
DataGridColumn(
    key="name",
    header="Name",
    editable=False,
)
DataGridColumn(
    key="quantity",
    header="Qty",
    editable=True,
    edit_accepts_unchanged=True,
    parser=int,
)
```

In this example, `quantity` intentionally keeps the default
`enter_behavior="activate"`. The `code` commit still advances into quantity
editing through `edit_next_column_key`, but after quantity is committed, the
next Enter activates the cell or row so product code can trigger backend work.
If the new row initializes `quantity` to `1`, pressing Enter immediately
accepts `1`; typing `5` before Enter commits `5`.

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
- sorting reorders only normal scrollable rows; pinned top and bottom rows keep
  their pinned regions and relative insertion order
- active row, selected rows, and selected cells are preserved by row/cell key
- if the active row no longer exists after mutation, active state repairs to
  the nearest enabled visible row
- `clear_sort()` restores insertion order for remaining rows, clears
  `sort_state`, preserves active/selection by key, and returns `True` only when
  a sort was active
- rows added while a sort is active receive insertion-order positions after all
  existing rows, but are displayed in current order until the caller sorts or
  clears sort

Custom sort functions are out of scope for the first implementation. If needed,
they can be added to `DataGridColumn` later without changing the V1
interaction model.

## Mutation API

Required methods:

- `add_row(row: DataGridRow | Mapping[str, object] | Sequence[object], *, index: int | None = None, activate: bool = False, edit_column_key: str | None = None) -> str`
- `remove_row(row_key: str) -> bool`
- `add_column(column: DataGridColumn, *, index: int | None = None, default: object = "") -> bool`
- `remove_column(column_key: str) -> bool`
- `update_cell(row_key: str, column_key: str, value: object | DataGridCell) -> bool`
- `clear() -> None`

Mutation rules:

- row and column keys must remain unique
- `activate=True` moves active row state to the added row
- `edit_column_key` implies `activate=True`, switches cursor mode to `cell`,
  moves active column state to that column, and starts editing when the cell is
  editable and enabled
- removing active row/column repairs active state
- removing selected rows/cells removes them from selection sets
- adding rows while a sort is active does not auto-sort; caller can call
  `sort_by()` again
- mutation during editing cancels editing unless the mutation is the successful
  edit commit for the active cell
- `clear()` removes all rows including pinned rows, clears selection, clears
  editing state, clears `sort_state`, and sets `active_row_key=None`
- `clear()` preserves columns, column configuration, `active_column_key` repair,
  cursor mode, selection mode, viewport settings, theme, and focus state
- callers remove columns with `remove_column()`; a future slice may add
  `clear_columns()` if needed

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
6. `theme_token_for_value`
7. formatter result token
8. cell theme token
9. selected token
10. focus token
11. editing or edit-error token

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
- pinned top/bottom rows render in fixed regions and are skipped by
  navigation, sorting, selection, editing, and activation
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
- column `enter_behavior="edit"` and `edit_next_column_key` data-entry flow
- `add_row(..., edit_column_key=...)` starts editing a new row's target cell
- prefilled editable cells accept unchanged default values on Enter when
  `edit_accepts_unchanged=True`
- `edit_next_column_key` can skip display-only columns
- edit commit followed by product-side `update_cell()` for dependent cells such
  as code-to-name lookup
- asynchronous-style dependent cell updates do not cancel edit-next flow when
  they update non-active cells
- final-cell activation followed by product-side row append and pinned total
  row update
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

## Review Decisions Closed

The initial spec review raised blockers around unresolved V1 decisions, row-key
normalization, active-state repair, selection return contracts, edit buffer
semantics, formatter output, and `clear_sort()` / `clear()` behavior. This
revision resolves those decisions in the sections above so implementation
planning can derive deterministic tasks and tests.
