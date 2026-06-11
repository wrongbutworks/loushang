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

P0A, P0B, P0C, P1A, P1B, P1C, P1D, and P1E widgets accept `ThemeResolver`
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
