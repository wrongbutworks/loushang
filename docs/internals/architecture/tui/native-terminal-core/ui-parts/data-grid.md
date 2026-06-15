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
- `DataGridFilterMode`
- `DataGridFilterPredicate`
- `DataGridRowView`
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

## Filtering

Filtering is a view concern. It does not remove rows from the stored row set:

- `row_keys` remains all stored row keys in current logical order.
- `view_row_keys` is the filtered body-row view.
- `filtered_row_count` is `len(view_row_keys)`.
- `total_body_row_count` is the non-pinned body-row count before filtering.

`set_filter_query(query, columns=None, mode="contains", case_sensitive=False)`
adds a built-in raw-value search over visible searchable columns. The default
search is case-insensitive. `case_sensitive=True` preserves case. `None` cell
values search as an empty string. Hidden columns and columns with
`searchable=False` are skipped by built-in query search.

`set_filter_predicate(predicate)` installs caller-owned business filtering. The
predicate receives `DataGridRowView`, a read-only row view with row key, raw
values, label, and disabled state. Query and predicate filters combine with
AND semantics. `clear_filter()` clears both filters.

Filter controls are not DataGrid children. Product pages compose one or more
`TextInput`, menu, toggle, or other controls above the grid and feed their
combined state into query and predicate setters. This keeps a single search box,
1-n column-specific filter boxes, and mixed enum/numeric filters as page
composition rather than a header-row feature.

Activation, keyboard navigation, Space selection, and `select_all()` operate on
the current body view. Pinned rows remain rendered in their pinned regions but
are excluded from filter counts and view row keys. Filtering does not delete
existing selected keys when the underlying rows still exist; hidden selections
are simply not rendered until the row returns to the view.

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

`ctrl-f` and `ctrl-b` are DataGrid navigation aliases for `pageDown` and
`pageUp` in non-editing row and cell modes. Editing cells keep the edit buffer
focused; those shortcuts are not treated as grid paging while an edit is open.

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
- `set_column_hidden()`
- `toggle_column()`
- `move_column()`
- `set_column_width()`
- `update_cell()`
- `clear()`
- `sort_by()`
- `clear_sort()`
- `cycle_sort()`

Mutations repair active state and selection by key. `replace_rows()` preserves
explicit keys when they still exist; shorthand replacement rows are new rows.
Column controls hide and reveal columns without dropping cell data, reorder
columns by key, and switch a column between fixed and flexible width. Hidden
columns are skipped by rendering, navigation, editing, selection, and sorting.
When a query filter has explicit columns, hiding or removing those columns
repairs `filter_query_columns` and recomputes the body view.

## Sorting

`sort_by(column_key, direction="asc")` sorts body rows by raw cell value and
preserves pinned rows in their pinned regions. `clear_sort()` restores insertion
order for remaining rows. `cycle_sort(column_key=None)` is the keyboard-friendly
helper for examples and pages:

```text
none -> asc -> desc -> none
```

When no column key is supplied, `cycle_sort()` targets the active column. Sorted
headers render an ASCII marker on the active sorted column: `^` for ascending
and `v` for descending. Sorting preserves filters; the filtered body view is
recomputed from the newly sorted logical order.

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
- query filtering, predicate filtering, and view-key repair
- filtering interaction with activation, selection, pinned rows, and editing
- sorting, sort cycling, header markers, and mutation repair
- 10k-row rendering that formats only visible rows
