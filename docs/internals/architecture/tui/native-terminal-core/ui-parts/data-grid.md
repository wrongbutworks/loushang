# DataGrid

`DataGrid` is the reusable advanced table widget for `loushang.tui`. Use it
when a page needs cell focus, column focus, horizontal viewport behavior, fixed
columns, pinned rows, selection, inline editing, sorting, or mutable row/cell
updates. Keep `Table` for compact row-oriented data.

## Public Shape

The public names are exported from `loushang.tui`, `loushang.tui.ui_parts`, and
`loushang.tui.ui_parts.widgets`:

- `DataGrid`
- `DataGridColumn`
- `DataGridRow`
- `DataGridCell`
- `DataGridSelect`
- `DataGridSelectionChange`
- `DataGridEdit`
- `TextFormatter`
- `NumberFormatter`
- `PercentFormatter`
- `DeltaFormatter`
- `CompactNumberFormatter`

`DataGrid` is stateful. It stores active row and column by key, not by index.
Rows can be explicit `DataGridRow` objects or shorthand mapping/list/tuple rows.
Shorthand rows receive generated `row-<n>` keys; durable refresh state should
use explicit keys.

Convenience adapters are available when callers already have common data
shapes:

- `DataGrid.from_records(records, columns=None, row_key_field=None, **grid_options)`
- `DataGrid.from_json(data, records_key="records", columns=None, row_key_field=None, **grid_options)`
- `DataGrid.from_csv(data, columns=None, row_key_field=None, dialect="excel", csv_options=None, **grid_options)`

`from_records()` accepts mapping records and infers columns from first-seen key
order when columns are not supplied. `from_json()` accepts a JSON text payload,
a top-level record list, or an object containing a `records` list. `from_csv()`
uses `csv.DictReader`, expects a header row, and keeps cell values as strings.
The adapters are thin constructor helpers; they do not infer numeric types,
formatters, validators, or editing rules.

## Rendering

Rendering owns:

- header rows
- optional row labels
- pinned top and bottom rows
- scrollable body viewport
- left fixed columns and active-column horizontal windowing
- row, cell, and column cursor declarations
- width-safe truncation through the shared cell-width helpers

Pinned rows are visible but non-interactive in V1. They are skipped by
navigation, selection, sorting, editing, and activation.

## Input

`cursor_mode` controls the active target:

- `row`: up/down/home/end move enabled rows; Enter activates a row.
- `cell`: vertical movement changes rows and horizontal movement changes
  enabled cells; Enter activates a cell unless the column starts editing.
- `column`: left/right/home/end move visible columns; Enter activates a column.
- `none`: input is not consumed.

Space is the selection input. Single selection replaces the current row/cell
selection. Multi selection toggles rows, cells, or all enabled cells in the
active column.

## Editing

Inline editing is intentionally text-based. `start_edit()` initializes the edit
buffer from the raw cell value. The first printable input replaces that selected
initial buffer; later text appends. Enter parses, validates, updates the raw
cell value, and returns `DataGridEdit`. Escape cancels.

In `cell` mode, printable text on an editable active cell starts editing
immediately. While editing, left/right/home/end move the text cursor inside the
edit buffer; they do not leave the cell. Up/down/page keys are consumed without
moving grid focus. Tab and shift+tab commit and try to continue editing the
next or previous editable cell. Editing cells render their edit buffer
left-aligned even when the column display alignment is right or center aligned,
so terminal block cursors move predictably as text is typed. `activate_cell(row_key,
column_key)` lets a wrapper move focus to an enabled cell without entering
editing.

Column parsers and validators belong to `DataGridColumn`. Product code handles
domain side effects after it receives `DataGridEdit`.

## Mutation

The mutation API includes:

- `add_row()`
- `replace_rows()`
- `remove_row()`
- `add_column()`
- `remove_column()`
- `update_cell()`
- `clear()`
- `sort_by()`
- `clear_sort()`

Mutations repair active state and selection by key. `replace_rows()` preserves
explicit keys when they still exist; shorthand replacement rows are new rows.

## Formatters

Built-in formatters are display-only:

- `TextFormatter`
- `NumberFormatter`
- `PercentFormatter`
- `DeltaFormatter`
- `CompactNumberFormatter`

They do not mutate state. Records, JSON, and CSV input adapters are explicit
classmethods instead of implicit constructor guessing. DataFrame support remains
future work and should not add a pandas dependency to the base TUI package.

## Theme Tokens

Core tokens:

- `widget.dataGrid.header`
- `widget.dataGrid.row`
- `widget.dataGrid.rowAlternate`
- `widget.dataGrid.focusRow`
- `widget.dataGrid.focusCell`
- `widget.dataGrid.editable`
- `widget.dataGrid.focusEditable`
- `widget.dataGrid.focusColumn`
- `widget.dataGrid.selectedRow`
- `widget.dataGrid.selectedCell`
- `widget.dataGrid.disabled`
- `widget.dataGrid.empty`
- `widget.dataGrid.fixedColumn`
- `widget.dataGrid.editing`
- `widget.dataGrid.editError`

Semantic tokens:

- `widget.dataGrid.positive`
- `widget.dataGrid.negative`
- `widget.dataGrid.neutral`
- `widget.dataGrid.warning`
- `widget.dataGrid.error`

## Tests

Changes to DataGrid should cover:

- public re-exports
- formatter behavior
- row and cell normalization
- row/cell/column/none navigation
- cursor declarations
- pinned rows and viewport repair
- fixed columns and horizontal active-column windowing
- activation and selection
- inline editing
- sorting and mutation repair
- 10k-row rendering that formats only visible rows
