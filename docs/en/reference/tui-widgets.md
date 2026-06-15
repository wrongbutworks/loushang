# TUI Widgets

English | [中文](../../zh-CN/reference/tui-widgets.md)

`loushang.tui` provides a first batch of reusable keyboard-friendly widgets.
They are ordinary `Renderable` and `Focusable` UI parts, so they work with
`Tui`, `SurfaceHost`, extension widgets, and modal surfaces.

For lifecycle wiring, see [TUI Runner](tui-runner.md). For editing behavior,
see [TUI Editing](tui-editing.md).

## P0A Widgets

| Widget | Use it for |
| --- | --- |
| `Button` / `IconButton` | One-line actions. |
| `Checkbox` | Boolean form values. |
| `Toggle` | Compact on/off settings. |
| `RadioGroup` | Mutually exclusive choices. |
| `TextField` | Labeled single-line text input backed by `TextInput`. |
| `SelectList` | Selection lists backed by `SelectionSurface`. |
| `Form` / `FormRow` | Local focus traversal and synchronous validation. |
| `Dialog` / `ConfirmDialog` | Modal composition and confirm/cancel flows. |

## P0B Small Controls

| Widget | Use it for |
| --- | --- |
| `Badge` | Compact metadata labels such as `beta`, `cached`, or counts. |
| `StatusPill` | Semantic state labels such as `ready`, `warning`, or `failed`. |
| `ProgressBar` | Static one-line progress with optional label and percent text. |
| `KeyValueList` / `KeyValueItem` | Dense property summaries and detail panes. |
| `Toolbar` / `ToolbarAction` | Horizontal action groups with local focus and activation. |

Small controls are plain `Renderable` parts except for `Toolbar`, which handles
only its own local focus. They are intended for dashboards, dialogs, status
panels, and extension surfaces that need compact reusable rows.

```python
from loushang.tui import Badge, KeyValueList, ProgressBar, StatusPill, Toolbar, ToolbarAction

header = (Badge("beta", kind="info"), StatusPill("ready", status="success"))
progress = ProgressBar(value=42, total=100, label="Indexing", width=12)
details = KeyValueList([("Model", "Kimi"), ("Mode", "safe")])
toolbar = Toolbar([ToolbarAction("Refresh", value="refresh"), ToolbarAction("Cancel", value="cancel")])
toolbar.focus()
```

## P0C Light Controls

| Widget | Use it for |
| --- | --- |
| `Menu` / `MenuItem` | Short vertical action lists with local focus and activation. |
| `Tabs` / `TabItem` | Horizontal selected-value controls for view switching. |
| `Spinner` | Static caller-driven activity indicators. |

`Menu` and `Tabs` handle only their local state. `Spinner` is display-only: the
caller passes `frame` and decides when to request another render.

```python
from loushang.tui import Menu, MenuItem, Spinner, TabItem, Tabs

tabs = Tabs([TabItem("overview", "Overview"), TabItem("logs", "Logs")])
menu = Menu([MenuItem("open", "Open"), MenuItem("refresh", "Refresh")])
spinner = Spinner(label="Syncing", frame=1)
```

## P1A Data Controls

| Widget | Use it for |
| --- | --- |
| `Table` / `TableColumn` / `TableRow` | Dense row/column data with local active-row navigation. |
| `DataGrid` / `DataGridColumn` / `DataGridRow` | Interactive grids with row, cell, and column cursors, selection, editing, sorting, and mutation. |

`Table` supports fixed and flexible columns, left and right alignment, disabled
rows, local keyboard navigation, and row activation.

```python
from loushang.tui import Table, TableColumn, TableRow

table = Table(
    [TableColumn("job", "Job"), TableColumn("status", "Status")],
    [TableRow("build", {"job": "Build", "status": "ready"})],
)
table.focus()
```

`DataGrid` is the heavier data-control option. Use it when callers need cell
focus, horizontal viewport behavior, fixed columns, pinned summary rows,
selection, inline editing, sorting, or live row/cell mutation. `Table` remains
the smaller row-focused control.

```python
from loushang.tui import DataGrid, DataGridColumn, DataGridRow, NumberFormatter

grid = DataGrid(
    [
        DataGridColumn("job", "Job"),
        DataGridColumn("runs", "Runs", align="right", formatter=NumberFormatter(precision=0)),
    ],
    [DataGridRow("build", {"job": "Build", "runs": 12})],
    cursor_mode="cell",
)
grid.focus()
```

For common data sources, `DataGrid` also has explicit adapter constructors.
`from_records()` accepts mapping records and infers columns from first-seen key
order. `from_json()` accepts JSON text, a top-level record list, or an object
with a `records` list. `from_csv()` reads a header row with the standard
library CSV parser and keeps CSV cell values as strings.

```python
grid = DataGrid.from_csv(
    "symbol,price\nAAPL,196.45\nMSFT,421.10\n",
    row_key_field="symbol",
    cursor_mode="cell",
)
```

In `cell` mode, printable text on an editable active cell starts editing.
During editing, left/right move inside the edit buffer; Enter commits, Escape
cancels, and Tab commits toward the next editable cell. Edit buffers render
left-aligned even for right-aligned display columns.

## P1B Text Controls

| Widget | Use it for |
| --- | --- |
| `TextArea` | Multi-line form text with deterministic cursor and viewport behavior. |

`TextArea` preserves newlines, uses plain `enter` for newline insertion, and
can be embedded in `Form` and `Dialog` through `editor_input_target()`.

```python
from loushang.tui import TextArea

notes = TextArea(label="Notes", placeholder="Write notes", height=5)
notes.focus()
```

## P1C Dialog Inputs

| Widget | Use it for |
| --- | --- |
| `QuestionDialog` | Multi-line question-and-answer prompts that return structured intents. |

`QuestionDialog` embeds `TextArea`: plain `enter` inserts a newline, the default
`ctrl+enter` submits, and `escape` / `ctrl+c` cancel. Submits return
`question_submit` intents; callers decide how to use the answer.

```python
from loushang.tui import QuestionDialog

dialog = QuestionDialog(
    title="Add note",
    question="What should be remembered?",
    placeholder="Write a multi-line answer",
    required=True,
)
dialog.focus()
```

## P1D Tree Controls

| Widget | Use it for |
| --- | --- |
| `TreeNode` / `TreeView` | Static hierarchical data with local active-row navigation and expansion state. |

`TreeView` flattens visible nodes in preorder. `right` expands a collapsed
branch or moves to the first enabled direct child; `left` collapses an expanded
branch or moves to the nearest enabled visible parent. Activating an enabled
node returns `InputIntent(kind="select", text=value)` unless the node defines
`on_select`.

```python
from loushang.tui import TreeNode, TreeView

tree = TreeView(
    (
        TreeNode("src", "src", expanded=True, children=(TreeNode("widgets", "widgets"),)),
        TreeNode("tests", "tests"),
    )
)
tree.focus()
```

## P1E Toast Controls

| Widget | Use it for |
| --- | --- |
| `Toast` / `ToastStack` | Inline transient messages with queueing, expiration, and dismissal. |

`Toast` is the message payload. `ToastStack` owns the queue and renders the
currently visible toasts wherever the caller places it. Toast controls do not
open overlays automatically; callers that want overlay presentation should put a
`ToastStack` in their own overlay or surface.
`ToastStack` is a pure renderable: it does not start timers, schedule renders,
open overlays, or prune expired toasts automatically.

Queue operations are explicit. `push()` appends a `Toast` or string message and
returns the stable toast value. `dismiss(value)` removes a dismissible toast,
`dismiss_oldest()` removes the oldest visible dismissible toast, `clear()`
removes all queued toasts, and `prune_expired()` mutates the queue by dropping
expired toasts. `all_toasts()` returns the stored queue, while
`visible_toasts()` filters expired entries, applies `max_visible`, and respects
`newest_on_top`.

Expiration is based on `created_at_ms + duration_ms`. The default duration is
4000 ms; `duration_ms=None` keeps a toast visible until it is dismissed or
cleared. Rendering and `visible_toasts()` hide expired toasts without mutating
the queue, so call `prune_expired()` when stored expired entries should be
removed.

```python
from loushang.tui import ToastStack

stack = ToastStack()
stack.push("Saved", kind="success", title="Config")
```

## P2A Command Palette

| Widget | Use it for |
| --- | --- |
| `CommandPaletteView` | Searchable action/model pickers backed by `CommandPalette` data. |

`CommandPalette` remains the data model used by coding adapters.
`CommandPaletteView` is the focusable widget that renders those items,
filters them with simple case-insensitive substring matching, and returns
structured intents. Selecting an enabled item returns `command_select`; cancel
returns `command_cancel`. When the close flags are enabled, the widget also
emits `surface_close`.

Disabled commands stay visible in `CommandPaletteView`, but keyboard navigation
skips them and activation returns nothing. Legacy coding palette adapters do
not consume the `disabled` flag in this slice.

```python
from loushang.tui import CommandPalette, CommandPaletteItem, CommandPaletteView

palette = CommandPalette(
    (
        CommandPaletteItem("deploy", "Deploy service", "Run deployment pipeline"),
        CommandPaletteItem("archive", "Archive release", "unavailable", disabled=True),
    ),
    title="Commands",
)
view = CommandPaletteView(palette)
view.focus()
```

## P2B Tabbed Content

| Widget | Use it for |
| --- | --- |
| `TabGroup` / `TabPage` | Tab header plus persistent page content. |
| `SearchableList` / `SearchableListItem` | Searchable long lists that can live inside a tab page. |

`TabGroup` composes existing `Tabs` with persistent page content. It keeps
`ContentSwitcher` internal and returns a structured tab-change object when the
selected page changes without a callback.

`SearchableList` owns query text, filtered items, active row, viewport offset,
and structured selection. It does not edit settings or write configuration.

## Settings Pages

Build new settings pages by composing `PageScaffold`, `Tabs` or `TabGroup`,
`SearchableList`, and focused controls such as `Toggle`, `RadioGroup`, and
`SelectList`. Product adapters should own setting ids, value cycling,
persistence, and side effects.

## Forms

```python
from loushang.tui import Checkbox, Choice, Form, FormRow, RadioGroup, TextField, Toggle

form = Form(
    [
        FormRow("name", TextField(label="Name", value="tower")),
        FormRow("cache", Checkbox("Enable cache", checked=True)),
        FormRow("mode", RadioGroup([Choice("fast", "Fast"), Choice("safe", "Safe")])),
        FormRow("auto", Toggle("Auto approve")),
    ]
)
form.focus()
```

`Form` owns only local traversal. `tab` and `shift+tab` move between direct
focusable rows. `FormRow` owns the stable field id used by `values()` and
`validate()`.

## Select Lists

`SelectList` defaults to embedded behavior:

```python
SelectList(items, close_on_escape=False)
```

With the default, `escape` returns `None` so a parent form or dialog decides
whether to close. Use `close_on_escape=True` for popup-style lists that should
emit `surface_close`.

## Dialogs

When opening a modal dialog, make the dialog itself the surface focus target:

```python
dialog = ConfirmDialog(title="Apply changes?", body=form)
tui.show_overlay(dialog, focus_target=dialog, presentation="modal", anchor="center")
```

The dialog handles `escape` and `ctrl+c` before delegating to nested fields. It
also delegates `editor_input_target()` to the active editable body child while
body focus is active.

## Theme Tokens

P0A, P0B, P0C, P1A, P1B, P1C, P1D, P1E, and P2A widgets accept `ThemeResolver`
where styling is supported. Initial stable tokens are:

| Token | Applies to |
| --- | --- |
| `widget.focus` | Focused enabled controls or rows. |
| `widget.disabled` | Disabled controls or disabled radio options. |
| `widget.error` | `TextField` and `FormRow` error lines. |
| `widget.field.label` | `TextField` labels. |
| `widget.field.help` | `TextField` help lines. |
| `widget.button.default` | Default buttons. |
| `widget.button.primary` | Primary buttons. |
| `widget.button.danger` | Danger buttons. |
| `widget.button.ghost` | Ghost buttons. |
| `widget.dialog.title` | Dialog titles. |
| `widget.dialog.action` | Dialog action rows. |
| `widget.question.title` | `QuestionDialog` title rows. |
| `widget.question.text` | `QuestionDialog` question rows. |
| `widget.question.action` | Inactive `QuestionDialog` action rows. |
| `widget.question.focus` | Active `QuestionDialog` action rows. |
| `widget.badge.default` | Default badges. |
| `widget.badge.info` | Informational badges. |
| `widget.badge.success` | Successful badges. |
| `widget.badge.warning` | Warning badges. |
| `widget.badge.danger` | Dangerous or failed badges. |
| `widget.status.neutral` | Neutral status pills. |
| `widget.status.info` | Informational status pills. |
| `widget.status.success` | Successful status pills. |
| `widget.status.warning` | Warning status pills. |
| `widget.status.danger` | Dangerous or failed status pills. |
| `widget.progress.track` | Progress bar unfilled track. |
| `widget.progress.fill` | Progress bar filled region. |
| `widget.progress.label` | Progress label and numeric text. |
| `widget.keyValue.key` | Key column in `KeyValueList`. |
| `widget.keyValue.value` | Value column in `KeyValueList`. |
| `widget.toolbar.action` | Enabled toolbar actions. |
| `widget.toolbar.focus` | Focused toolbar action. |
| `widget.toolbar.disabled` | Disabled toolbar actions. |
| `widget.menu.item` | Enabled inactive menu items. |
| `widget.menu.focus` | Focused active menu item. |
| `widget.menu.disabled` | Disabled menu items. |
| `widget.menu.description` | Menu item descriptions. |
| `widget.tabs.tab` | Enabled unselected tabs. |
| `widget.tabs.selected` | Selected tab when the tab strip is not focused. |
| `widget.tabs.focus` | Selected tab while the tab strip is focused. |
| `widget.tabs.disabled` | Disabled tabs. |
| `widget.spinner.frame` | Spinner frame glyph. |
| `widget.spinner.label` | Spinner label text. |
| `widget.table.header` | Table header rows. |
| `widget.table.row` | Enabled inactive table rows. |
| `widget.table.focus` | Focused active table row. |
| `widget.table.disabled` | Disabled table rows. |
| `widget.table.empty` | Table empty-state text. |
| `widget.dataGrid.header` | DataGrid header rows. |
| `widget.dataGrid.row` | Enabled inactive DataGrid body rows. |
| `widget.dataGrid.rowAlternate` | Alternating DataGrid body rows when zebra stripes are enabled. |
| `widget.dataGrid.focusRow` | Focused active DataGrid row. |
| `widget.dataGrid.focusCell` | Focused active DataGrid cell. |
| `widget.dataGrid.editable` | Editable DataGrid cells when not actively editing. |
| `widget.dataGrid.focusEditable` | Focused editable DataGrid cell before editing starts. |
| `widget.dataGrid.focusColumn` | Focused active DataGrid column/header. |
| `widget.dataGrid.selectedRow` | Selected DataGrid rows. |
| `widget.dataGrid.selectedCell` | Selected DataGrid cells. |
| `widget.dataGrid.disabled` | Disabled DataGrid rows and cells. |
| `widget.dataGrid.empty` | DataGrid empty-state text. |
| `widget.dataGrid.fixedColumn` | DataGrid fixed columns. |
| `widget.dataGrid.editing` | DataGrid editing cell. |
| `widget.dataGrid.editError` | DataGrid editing validation errors. |
| `widget.dataGrid.positive` | Positive numeric or semantic DataGrid values. |
| `widget.dataGrid.negative` | Negative numeric or semantic DataGrid values. |
| `widget.dataGrid.neutral` | Neutral DataGrid values. |
| `widget.dataGrid.warning` | Warning DataGrid states. |
| `widget.dataGrid.error` | Error DataGrid states. |
| `widget.tree.row` | Enabled inactive tree rows. |
| `widget.tree.focus` | Focused active tree row. |
| `widget.tree.disabled` | Disabled tree rows. |
| `widget.tree.empty` | Tree empty-state text. |
| `widget.toast.info` | Informational toast prefix. |
| `widget.toast.success` | Successful toast prefix. |
| `widget.toast.warning` | Warning toast prefix. |
| `widget.toast.danger` | Dangerous or failed toast prefix. |
| `widget.toast.title` | Toast title segment. |
| `widget.toast.message` | Toast message segment. |
| `widget.commandPalette.title` | `CommandPaletteView` title rows. |
| `widget.commandPalette.queryLabel` | `CommandPaletteView` search labels. |
| `widget.commandPalette.queryText` | `CommandPaletteView` query text. |
| `widget.commandPalette.placeholder` | `CommandPaletteView` placeholder text. |
| `widget.commandPalette.section` | `CommandPaletteView` section labels. |
| `widget.commandPalette.item` | Enabled inactive command rows. |
| `widget.commandPalette.focus` | Focused active command rows. |
| `widget.commandPalette.disabled` | Disabled command rows. |
| `widget.commandPalette.description` | Command descriptions. |
| `widget.commandPalette.empty` | Command palette empty-state text. |
| `widget.commandPalette.footer` | Command palette footer rows. |
| `widget.textArea.label` | `TextArea` label rows. |
| `widget.textArea.placeholder` | `TextArea` placeholder text. |
| `widget.textArea.text` | `TextArea` body text. |
| `widget.textArea.error` | `TextArea` error rows. |
| `widget.textArea.help` | `TextArea` help rows. |

## Planned Catalog

`Popover` is a planned catalog entry. It is not part of the current widget
implementation.

## Example

- [examples/tui/43_widgets_foundation.py](../../../examples/tui/43_widgets_foundation.py):
  small keyboard-only widget app with a form and confirm dialog.
- [examples/tui/44_widgets_small_controls.py](../../../examples/tui/44_widgets_small_controls.py):
  compact status, details, progress, and toolbar composition.
- [examples/tui/45_widgets_light_controls.py](../../../examples/tui/45_widgets_light_controls.py):
  light menu, tabs, and spinner composition.
- [examples/tui/46_widgets_table.py](../../../examples/tui/46_widgets_table.py):
  dense table composition with keyboard row selection.
- [examples/tui/47_widgets_textarea.py](../../../examples/tui/47_widgets_textarea.py):
  multi-line text entry inside a small form.
- [examples/tui/48_widgets_question_dialog.py](../../../examples/tui/48_widgets_question_dialog.py):
  multi-line question dialog with structured submit and cancel intents.
- [examples/tui/49_widgets_tree.py](../../../examples/tui/49_widgets_tree.py):
  static hierarchical tree with keyboard expansion and selection.
- [examples/tui/50_widgets_toast.py](../../../examples/tui/50_widgets_toast.py):
  inline toast stack with queue, dismissal, and clear actions.
- [examples/tui/51_widgets_command_palette.py](../../../examples/tui/51_widgets_command_palette.py):
  searchable command palette with filtering, navigation, selection, and cancel.
- [examples/tui/52_widgets_tabgroup_searchable_list.py](../../../examples/tui/52_widgets_tabgroup_searchable_list.py):
  tabbed settings-style pages with searchable long lists.
- [examples/tui/53_widgets_page_scaffold.py](../../../examples/tui/53_widgets_page_scaffold.py):
  reusable page chrome with header, body, footer, and focus routing.
- [examples/tui/54_widgets_settings_page_assembly.py](../../../examples/tui/54_widgets_settings_page_assembly.py):
  settings page assembly using page, tabs, and searchable list widgets.
- [examples/tui/55_widgets_tree_page_scaffold.py](../../../examples/tui/55_widgets_tree_page_scaffold.py):
  tree view inside a reusable page scaffold.
- [examples/tui/56_widgets_table_page_scaffold.py](../../../examples/tui/56_widgets_table_page_scaffold.py):
  table view inside a reusable page scaffold.
- [examples/tui/57_widgets_directory_tree.py](../../../examples/tui/57_widgets_directory_tree.py):
  directory tree rendering and navigation.
- [examples/tui/58_widgets_datagrid.py](../../../examples/tui/58_widgets_datagrid.py):
  interactive DataGrid scenarios with editing, sorting, fixed columns, and mutation.
- [examples/tui/59_widgets_datagrid_adapters.py](../../../examples/tui/59_widgets_datagrid_adapters.py):
  DataGrid construction from records, JSON, and CSV sources.
