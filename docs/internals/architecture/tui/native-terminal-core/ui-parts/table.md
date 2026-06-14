# Table

`Table` is a reusable focused widget for row-oriented tabular data. It is
intended for compact queues, status lists, run summaries, and other bounded
tables where the active unit is a row.

It owns row normalization, column width allocation, row focus, disabled-row
skipping, activation, viewport windowing, alignment, and row/header styling.
Product pages still own selected detail panels, data loading, sorting policy,
mutation, and global footer/status text.

Table is not a full DataGrid. It does not own cell focus, horizontal scrolling,
column resizing, inline editing, multi-select, pinned columns, or sortable
headers. Those behaviors should be designed as a separate DataGrid contract.

## Inputs And State

- `TableColumn(key, header, width=None, min_width=1, align="left")`.
- `TableRow(value, cells, disabled=False, on_select=None)`.
- `rows`: `TableRow`, mapping rows, or sequence rows.
- `active_index`: initial active row index.
- `show_header`: whether to render the header row.
- `empty_text`: text shown when there are no rows.
- `wrap`: whether up/down navigation wraps between first and last enabled rows.
- `theme`: optional `ThemeResolver`.

Mapping rows resolve cells by column key. Sequence rows resolve cells by column
position. Non-`TableRow` inputs derive their row value from the first non-empty
cell, falling back to the row index.

## Layout Behavior

Rendering order is:

1. optional header row
2. visible body row viewport, or one empty row when there are columns but no
   rows

The left focus prefix consumes up to two columns. Remaining width is allocated
to visible columns. Fixed-width columns keep their requested width when
possible; flexible columns share remaining space. If the table is still too
wide, columns shrink from right to left until the rendered line fits.

Rows and cells are truncated to the available width. Right-aligned columns pad
on the left. When focused, Table declares a cursor at column 0 on the active
visible body row so parent layouts can offset it through page chrome.

## Focus And Activation

Table handles these keys when focused:

- `up` / `down`: move between enabled rows.
- `home` / `end`: jump to the first or last enabled row.
- `enter` / `space`: run `on_select` or return the row value.

Disabled rows remain visible but are skipped by navigation and cannot be
activated.

Table does not define a page-level focus escape. A wrapper page may translate
an edge result, for example `up` on the first enabled row, into `None` so
`PageScaffold` or `TabGroup` can move focus to a header.

## Theme Tokens

| Token | Applies to |
| --- | --- |
| `widget.table.header` | Optional header row |
| `widget.table.row` | Normal enabled body rows |
| `widget.table.focus` | Active body row while Table has focus |
| `widget.table.disabled` | Disabled body rows |
| `widget.table.empty` | Empty table row |

## Composition

Table can live directly inside page content, inside a page object that adds a
detail panel below or beside the table, or inside `PageScaffold` body content.
Parent pages should preserve Table's cursor declaration when adding local
chrome, then let `PageScaffold` offset the body cursor through header,
separator, padding, and footer rows.

Use page-level footer/status components for global commands and state. Keep
Table rows limited to tabular navigation and row labels.

## Test Obligations

Changes to Table should cover:

- mapping, sequence, and `TableRow` normalization
- fixed/flexible column width allocation and right-to-left shrinking
- left/right alignment and width truncation
- disabled-row visibility and navigation skipping
- up/down/home/end movement with and without wrapping
- activation callback and row-value results
- bounded viewport and cursor declaration on the active visible body row
- header-hidden and empty-state rendering
- theme tokens preserving visible text
- composition playback with `PageScaffold` when cursor offsets matter
