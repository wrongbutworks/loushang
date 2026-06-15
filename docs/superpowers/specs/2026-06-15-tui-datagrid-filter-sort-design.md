# TUI DataGrid Filter And Sort Design

## Status

Draft for spec review.

This is a TUI-lane design for extending the reusable `DataGrid` widget with
filter/search and sort UX support. The spec is temporary in
`docs/superpowers/specs`. After implementation, the durable widget contract
should be summarized under
`docs/internals/architecture/tui/native-terminal-core/ui-parts/data-grid.md`.

## Context

`DataGrid` V1 already supports row, cell, and column cursor modes, fixed
columns, inline editing, selection, mutation APIs, adapters, explicit sorting,
and large bounded rendering. The current large-data example demonstrates 2,000
rows, page jumps, and page controls.

The next common product need is filtering a long grid. Some pages need a single
global search box. Other pages need a small filter bar with 1-n controls, such
as:

```text
Search: [cloud]    Sector: [AI]    Status: [active]    Min price: [100]
Go to page: [1   ] / 12
```

Those controls should not be hard-coded into `DataGrid`. They are page layout
and focus-composition concerns. The widget should provide a stable row-view
pipeline, filter APIs, counts, and active-state repair. Pages can then compose
one search input, many field inputs, menus, toggles, or page-jump controls
above the grid.

## Problem

Without a shared filter contract, each DataGrid page will invent its own
filtered row set, active-row repair, selected-key behavior, counts, and empty
state. That will create inconsistent navigation and make examples unreliable.

There is also a subtle existing contract to preserve:

- `row_keys` is the public list of all grid rows in the current logical order.
- `sort_by()` currently reorders that logical order.
- Existing examples use `row_keys`, `activate_row()`, and stable row keys.

Filtering must therefore affect the grid view without destroying the row store
or changing the meaning of `row_keys`.

## Goals

- Add a built-in DataGrid row-filtering contract.
- Support a simple global query over visible searchable columns.
- Support caller-provided predicates for multi-control business filters.
- Allow query and predicate filters to combine with AND semantics.
- Keep filter controls outside DataGrid so pages can build 1-n inputs.
- Preserve existing `row_keys` and `sort_by()` public behavior.
- Add `view_row_keys` and row counts for filtered views.
- Repair active row, visible window, editing state, and navigation after filter
  changes.
- Keep selection by key across filtering when the underlying row still exists.
- Add sort UX helpers and examples without requiring mouse support.
- Extend the large-data example into a filter, sort, and page-navigation demo.
- Keep large data behavior bounded: filtering may scan source rows, but render
  must not format or draw every row.

## Non-Goals

- Do not add a header-embedded per-column filter row in this slice.
- Do not add TextInput fields inside `DataGrid`.
- Do not add server-side filtering, remote pagination, or async loading.
- Do not add complex query language, regex, SQL-like expressions, or fuzzy
  ranking.
- Do not add mouse sort clicks or hover controls.
- Do not add column-level filter UI widgets as DataGrid children.
- Do not change `Table`.
- Do not migrate product settings pages in this slice.

## Core Decisions

### 1. DataGrid Owns Filtering Semantics, Not Filter Controls

`DataGrid` owns:

- current query filter state
- current predicate filter state
- filtered body-row view
- counts
- active repair
- selection/render/navigation behavior under filtering

The caller owns:

- one or more `TextInput` controls
- menus or toggles for enum filters
- focus order among filter controls, page controls, and the grid
- domain parsing for numeric filters
- footer wording and page-specific status messages

This keeps the widget reusable. A stock watchlist, an order-entry table, and a
CI job table can all use the same DataGrid filter API while building different
controls above it.

### 2. Filtering Is View-Only

Filtering does not remove rows and does not reorder the all-row store.

- `row_keys` remains all rows in the current logical order.
- `view_row_keys` is new and returns filter-visible body row keys.
- `filtered_row_count` is the number of filter-visible body rows.
- `total_body_row_count` is the number of non-pinned body rows before filtering.

Navigation, activation, selection toggles, and viewport use the body view.
Rendering uses the rendered view. Mutation APIs continue to act on the all-row
store by key.

Use these terms precisely:

- **stored rows**: all normalized rows in current logical order, including
  pinned rows.
- **body rows**: stored rows where `pinned is None`.
- **body view**: body rows that match the active filters.
- **rendered view**: pinned top rows, the visible body-view window, and pinned
  bottom rows.

`view_row_keys` is body-view only. Pinned rows can still appear in the rendered
view, but they are not part of filter counts, row navigation, activation, or
selection actions.

### 3. Existing Sort Behavior Is Preserved

`sort_by(column_key, direction)` continues to reorder the all-row logical order
and update `row_keys`, matching current tests and examples. Filtering then
projects a view from that logical order.

Pinned rows are not sorted with body rows. Sorting produces this stored-row
order:

```text
pinned top rows in insertion order
-> sorted body rows
-> pinned bottom rows in insertion order
```

That order is reflected by `row_keys` and rendering.

In this slice the effective body pipeline is:

```text
stored rows in current logical order -> body rows -> filters -> viewport/render/navigation
```

When `clear_sort()` is called, the stored rows return to insertion order, then
the current filters are reapplied to the view.

### 4. 1-n Column Filters Are Composition, Not A Header Filter Row

The first-class API for multiple filters is a predicate. A page can combine any
number of controls into one predicate:

```python
grid.set_filter_query(search_input.value, columns=("symbol", "sector", "status"))
grid.set_filter_predicate(
    lambda row: (
        _sector_matches(row.values, sector_input.value)
        and _status_matches(row.values, status_input.value)
        and _min_price_matches(row.values, min_price_input.value)
    )
)
```

This avoids baking one UI shape into the core widget. A future `FilterBar`
helper can wrap this pattern if multiple examples converge on the same layout.

## Public API Additions

### Types

```python
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

DataGridFilterMode = Literal["contains", "prefix"]

@dataclass(frozen=True, slots=True)
class DataGridRowView:
    key: str
    values: Mapping[str, object]
    label: str | None = None
    disabled: bool = False

DataGridFilterPredicate = Callable[[DataGridRowView], bool]
```

`DataGridRowView` is a public read-only view passed to predicates. It avoids
exposing private normalized row types and gives predicates row key, raw cell
values, label, and disabled state. It does not expose mutation methods.

Implementation should build `values` as a read-only mapping, such as
`MappingProxyType`, so predicates cannot mutate grid internals by accident.

### DataGridColumn

Add one optional field:

```python
searchable: bool = True
```

The built-in query filter searches visible columns where `searchable=True`.
Hidden columns are not searched by the built-in query filter. A predicate can
still inspect hidden column values through `DataGridRowView.values` when the
caller needs domain-specific behavior.

### Phase 1 API: Filtering

Phase 1 adds filter/search state, counts, and view repair. It does not add sort
cycle helpers or header sort markers.

#### DataGrid Properties

Add:

```python
filter_query: str
filter_query_columns: tuple[str, ...] | None
filter_mode: DataGridFilterMode
filter_case_sensitive: bool
has_filter: bool
view_row_keys: tuple[str, ...]
filtered_row_count: int
total_body_row_count: int
```

Rules:

- `row_keys` remains all rows in current logical order.
- `view_row_keys` excludes pinned rows and includes only rows visible after
  filters.
- `filtered_row_count == len(view_row_keys)`.
- `total_body_row_count` excludes pinned top and bottom rows.
- `has_filter` is true when the query is non-empty or a predicate is installed.

#### DataGrid Methods

Add:

```python
def set_filter_query(
    self,
    query: str,
    *,
    columns: Sequence[str] | None = None,
    mode: DataGridFilterMode = "contains",
    case_sensitive: bool = False,
) -> bool: ...

def set_filter_predicate(self, predicate: DataGridFilterPredicate | None) -> bool: ...

def clear_filter(self) -> bool: ...
```

Method rules:

- `set_filter_query()` stores the effective stripped query in `filter_query`.
- By default, matching is case-insensitive using `casefold()`.
- `case_sensitive=True` preserves case during matching.
- Empty query clears only the query filter; it does not clear the predicate.
- Whitespace-only query is empty. It stores `filter_query=""`, stores
  `filter_query_columns=None`, resets `filter_mode="contains"`, resets
  `filter_case_sensitive=False`, and sets `has_filter=False` unless a predicate
  is installed.
- `columns=None` searches all visible searchable columns.
- Explicit `columns` are tolerant. Unknown, hidden, or `searchable=False`
  columns are ignored rather than raising.
- `filter_query_columns` stores the normalized accepted tuple for explicit
  columns. It remains `None` when the query searches all visible searchable
  columns.
- If no searchable columns remain, a non-empty query matches no rows.
- `mode="contains"` checks whether the query appears anywhere in a cell value.
- `mode="prefix"` checks whether a cell value starts with the query.
- Query matching uses raw cell values normalized by the `cell_text` rules below,
  not column formatters. This keeps display formatters render-only and avoids
  formatting every row during filtering.
- `set_filter_predicate(None)` clears only the predicate filter.
- Query filter and predicate filter combine with AND semantics.
- `clear_filter()` clears both query and predicate filters.
- Each method recomputes `view_row_keys` and repairs active row, viewport,
  editing state, and selection view.
- Methods return `True` when stored filter state or resulting `view_row_keys`
  changed.

Callers must call a filter setter whenever external filter inputs change.
Predicates often close over page state, but DataGrid cannot detect that closed
state changing by itself.

### Phase 2 API: Sort UX

Phase 2 adds:

```python
def cycle_sort(self, column_key: str | None = None) -> bool: ...
```

`cycle_sort()` is a keyboard-friendly helper for examples and pages. It chooses
the provided `column_key`, or the active column when omitted. It cycles:

```text
none -> asc -> desc -> none
```

If a different column is selected while another sort is active, the cycle starts
with ascending sort on the new column.

## Public Behavior Under Filtering

| Surface | Behavior |
| --- | --- |
| `row_keys` | All stored row keys in current logical order. Filtering never removes keys from this tuple. Sorting may reorder it, preserving current behavior. |
| `view_row_keys` | Filter-visible body row keys only. Excludes pinned top/bottom rows. Page controls and filtered navigation should use this tuple. |
| `active_row_key` | Either `None` or a key from the current body view. It must not point at a filtered-out, disabled, missing, or pinned row. |
| `activate_row(row_key)` | Returns `True` only for enabled body rows in the current body view. Returns `False` for missing, disabled, pinned, or filtered-out rows. With no active filter, this matches current behavior. |
| `activate_cell(row_key, column_key)` | Returns `True` only when the row is enabled and present in the current body view and the cell is enabled. Filtered-out rows return `False`. |
| Page navigation | Pages are computed from `view_row_keys`, not `row_keys`, whenever filters are active. A page jump activates the first enabled row on the target filtered page, or falls back to normal active-row repair if that page contains no enabled row. |
| Mutation by key | `remove_row()`, `update_cell()`, and related mutation APIs continue to operate on stored rows by key, even if a row is currently filtered out. |

## Filter Semantics

### Search Text

Built-in query search is intentionally plain:

- case-insensitive by default
- `contains` or `prefix`
- raw value based
- optionally case-sensitive through `set_filter_query(..., case_sensitive=True)`
- no regex
- no token grammar
- no fuzzy ranking

Examples can still provide richer behavior through predicates. For instance, a
stock page can parse a minimum price input and inspect `row.values["price"]`.

Cell text normalization:

- First compute `cell_text = "" if value is None else str(value)`.
- Case-insensitive matching compares `query.strip().casefold()` with
  `cell_text.casefold()`.
- Case-sensitive matching compares `query.strip()` with `cell_text`.

### Predicate Behavior

Predicates receive body rows only. They do not receive pinned top or bottom
rows.

Predicates are caller code. Predicate exceptions should propagate from the
filter operation that evaluates them, usually `set_filter_predicate()` or the
next filter-repair call. DataGrid should not silently treat exception rows as
non-matches because that hides product bugs and can make render behavior
non-deterministic.

Examples should validate user-entered filter values before installing a
predicate whenever possible. Invalid example controls should show a status
message and keep or clear the previous predicate explicitly.

### Pinned Rows

Pinned top and bottom rows bypass filters and remain in their pinned regions.
They are not included in `view_row_keys`, `filtered_row_count`, or
`total_body_row_count`.

This keeps summary rows, total rows, and fixed explanatory rows visible while
body rows filter underneath them.

Pinned rows are rendered but never activated by row navigation. Active repair,
Space, `select_all()`, and cell selection operate on the body view only.

`empty_text` describes an empty body view. If pinned rows exist and no body rows
match, render pinned rows and render one `empty_text` body line when vertical
space allows. If there are no pinned rows, the empty filtered grid renders the
same `empty_text` line by itself.

### Disabled Rows And Cells

Disabled body rows can be visible after filtering. They remain skipped by
navigation and selection just as they are today.

Disabled cells are included in query search because filtering is about row
visibility, not editability. If a page wants disabled cells to be ignored, it
should use a predicate.

### Hidden Columns

Hidden columns are skipped by built-in query search. This matches the principle
that simple search should search what the user can see.

Predicates can inspect hidden values because business filters often need hidden
IDs or status codes.

### Column Changes

When a query filter is active, column operations that change query eligibility
must update the filter view:

- `set_column_hidden()` re-normalizes explicit `filter_query_columns`, drops
  newly hidden columns, recomputes `view_row_keys`, and repairs state.
- `remove_column()` drops removed columns from explicit `filter_query_columns`,
  recomputes `view_row_keys`, and repairs state.
- If explicit query columns become empty while `filter_query` is non-empty, the
  query matches no body rows.
- `move_column()` and `set_column_width()` do not change query eligibility, but
  they may still use existing column-state repair rules.

## State Repair

After any filter change:

- If the active row is still enabled and visible, keep it.
- If the active row exists but is filtered out, move to the first enabled row in
  the body view.
- If there are no enabled rows in the body view, set `active_row_key=None`.
- Keep `active_column_key` repaired using the existing visible-column rules.
- If the active editing row is filtered out, cancel editing.
- Clamp `_first_visible_row_index` to the body view.
- If the body view is empty, set `_first_visible_row_index=0`.

Selection is key-based:

- Filtering does not delete selected rows or selected cells when the underlying
  row and column still exist.
- Rendering only marks selected keys that are currently visible.
- Space toggles selection only within the body view.
- `select_all()` selects only enabled rows or cells in the body view.
- With no active filter, `select_all()` preserves current behavior because the
  body view is the complete set of non-pinned body rows.
- Removing rows or columns still deletes missing keys from selection sets.

## Sorting UX

The core sorting methods are already present:

```python
sort_by(column_key: str, direction: DataGridSortDirection = "asc") -> bool
clear_sort() -> bool
sort_state: tuple[str, DataGridSortDirection] | None
```

This slice adds a sort cycle helper and visible header indicators.

Rules:

- `cycle_sort()` targets the active visible column when no column key is
  provided.
- Sorting a hidden, missing, or `sortable=False` column returns `False`.
- Header rendering marks the active sorted column with ASCII suffixes:
  - `^` for ascending
  - `v` for descending
- Width calculation and truncation must include the marker.
- Header markers use the existing header theme token, not a hard-coded color.
- Sorting a column while filters are active updates the stored logical order;
  the body view is then recomputed from that order.

Repair after `sort_by()`, `clear_sort()`, or `cycle_sort()`:

- Recompute the body view after the stored row order changes.
- Preserve `active_row_key` when that row is still enabled and present in the
  body view.
- If the active row is no longer available, repair to the first enabled row in
  the body view.
- Clamp or adjust `_first_visible_row_index` so the active row remains visible
  when possible.
- Preserve selected row and cell keys when the underlying rows and columns
  still exist.
- Do not clear active filters.

Recommended example keybinding:

- `s`: cycle sort on the active column in cell or column mode.
- For row mode, `s` sorts the first visible sortable column unless the example
  provides another active-column concept.

## Filter Bar Composition

V1 should demonstrate filter composition in an example, but not add a public
`FilterBar` class.

Recommended example focus order:

```text
Search -> Sector -> Status -> Min price -> Go to page -> DataGrid
```

Keyboard behavior:

- `Tab` moves to the next control.
- `Shift+Tab` moves to the previous control.
- `Ctrl+G` moves to the page input.
- `Esc` from any filter input returns focus to the grid without clearing the
  filter.
- Backspace and printable text are owned by the focused input, not by global
  shortcuts.
- `q` quits only when no text input or edit buffer owns the key.

Filter controls apply live on text changes. Invalid numeric filter text should
show a red status line in the example and preserve the last valid parsed value
for that numeric clause. If the numeric input is the only changed control, the
filtered view remains unchanged. The status text should make this explicit, for
example:

```text
Error: Min price must be a number; filters unchanged
```

If there is no previous valid numeric value, the invalid numeric control does
not add a numeric clause. Other valid controls can continue to update their
query or predicate state while the numeric clause remains frozen or absent.

The footer should include both row counts and sort state:

```text
Rows 41-60 of 327 filtered from 2,000 | Page 3/17 | Sort Price desc | Tab filters | s sort | q quit
```

When no rows match, the grid renders `empty_text` and the footer should still
show `0/2,000`.

## Example Plan

Add or update one example after Phase 1, then expand it in Phase 2.

### Phase 1 Example

Use the existing large dataset shape:

- 2,000 generated rows
- global search input
- page input
- DataGrid body
- footer with filtered count

It should verify:

- typing a search filters rows
- page count changes under filtering
- page input clamps to filtered pages
- active row repairs when the previous active row is filtered out
- `q` does not quit while a text input owns the key

### Phase 2 Example

Expand the example into a combined filter/sort demo:

- global `Search`
- `Sector`
- `Status`
- `Min price`
- `Go to page`
- DataGrid with active sort marker
- `s` cycles sort

The example should remain generic. It can be stock-like but must not become a
stock-specific widget.

## Test Requirements

### Phase 1 Tests

- `set_filter_query()` filters body rows by raw visible searchable cell values.
- Query matching is case-insensitive.
- `case_sensitive=True` preserves case during query matching.
- `prefix` and `contains` modes differ.
- Empty and whitespace-only query clears only the query filter and resets query
  columns, mode, and case sensitivity defaults.
- Predicate filter works from `DataGridRowView.values`.
- Predicate exceptions propagate instead of being silently swallowed.
- Predicate setters recompute even when caller replaces one predicate callable
  with another callable that closes over external state.
- Query and predicate combine with AND semantics.
- `None` cell values search as an empty string before case normalization.
- Hidden columns are not searched by built-in query.
- `searchable=False` columns are not searched by built-in query.
- Explicit query columns tolerate unknown, hidden, and `searchable=False`
  columns, and `filter_query_columns` stores only accepted columns.
- An all-invalid explicit column set with a non-empty query matches no body
  rows.
- Predicate can inspect hidden values.
- Pinned rows remain rendered and are excluded from `view_row_keys` and counts.
- Pinned rows plus an empty body view render pinned rows and an `empty_text`
  body line when height allows.
- Disabled matching rows remain visible but are skipped by navigation.
- `activate_row()` and `activate_cell()` return `False` for filtered-out,
  disabled, missing, and pinned rows.
- Page jumps activate the first enabled row on the target filtered page and
  repair normally when the page has no enabled rows.
- Active row stays when still visible.
- Active row repairs to first enabled visible row when filtered out.
- Active row becomes `None` when no enabled visible rows remain.
- Editing cancels when the editing row is filtered out.
- Selection keys survive filtering when source rows still exist.
- `select_all()` and Space only affect filtered visible enabled rows or cells.
- `row_keys` remains all rows and is not filtered.
- `view_row_keys` reflects the filtered view.
- Page navigation examples compute pages from `view_row_keys`, not `row_keys`,
  under filtering.
- Rendering an empty filtered view shows `empty_text`.
- Rendering still formats only visible rows after a filter is already applied.
- Hiding or removing explicit query columns re-normalizes
  `filter_query_columns`, recomputes `view_row_keys`, and repairs active state.

### Phase 2 Tests

- `cycle_sort()` cycles none to asc to desc to none.
- `cycle_sort()` on a different column starts at asc.
- `cycle_sort()` returns `False` for missing, hidden, or non-sortable columns.
- Header shows `^` and `v` markers for sorted column.
- Header marker does not overflow narrow columns.
- Sorting while filtered recomputes `view_row_keys`.
- Sorting with pinned rows keeps pinned top and bottom rows in pinned regions
  and sorts only body rows.
- Clearing sort preserves the active filters.
- Clearing filters preserves the active sort.
- Page navigation example reports filtered counts.
- Example playback covers Tab through filters, Ctrl+G page input, search text,
  sort cycling, and q behavior outside text inputs.
- Example playback covers invalid numeric filter text preserving the last valid
  predicate and showing an error status.

## Implementation Notes

- Keep implementation in `src/loushang/tui/ui_parts/widgets/data_grid.py` for
  this slice unless the file becomes unwieldy during planning.
- Prefer private helpers:
  - `_body_rows()`
  - `_pinned_top_rows()`
  - `_pinned_bottom_rows()`
  - `_view_body_rows()`
  - `_row_view(row)`
  - `_row_matches_filters(row)`
  - `_row_matches_query(row)`
  - `_repair_state_after_view_change()`
- Existing helpers that iterate `_enabled_rows()` need to switch to filtered
  view rows where they drive navigation, render, selection, or editing.
- Mutation APIs should continue to operate on `_rows` by key.
- `replace_rows()` should preserve filter state and reapply it to the new rows.
- `clear()` should clear filter state along with rows, selection, editing, and
  sort state.
- Avoid calling formatters during filter matching. Formatters remain
  display-only.
- Keep all new public exports aligned across:
  - `src/loushang/tui/ui_parts/widgets/__init__.py`
  - `src/loushang/tui/ui_parts/__init__.py`
  - `src/loushang/tui/__init__.py`

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Filtering accidentally changes `row_keys`. | Add direct tests that `row_keys` remains all rows under filtering. |
| Selection disappears under filtering. | Keep selection sets keyed to source rows and only scope selection actions to the current view. |
| Large filters become expensive. | Accept O(n) row scans on filter changes, but do not format/render all rows. |
| Header filter row becomes a layout trap. | Keep V1 filter controls caller-owned and demonstrate composition above the grid. |
| Sort/filter order confuses users. | Preserve existing sort semantics, then project filters over the current logical order. |
| Text inputs intercept global shortcuts inconsistently. | Example input routing must let focused inputs own printable text and Backspace before app shortcuts. |

## Open Follow-Up

A future `FilterBar` widget may be useful if two or more real pages converge on
the same control model. That should be a separate spec. The likely shape is a
small layout helper for named controls and focus routing, not a DataGrid
subcomponent.
