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

P0A, P0B, and P0C widgets accept `ThemeResolver` where styling is supported.
Initial stable tokens are:

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

## Planned Catalog

`Popover`, `PromptDialog`, `Table`, `TreeView`, `Toast`, and `TextArea` are
planned catalog entries. They are not part of the current widget implementation.

## Example

- [examples/tui/43_widgets_foundation.py](../../../examples/tui/43_widgets_foundation.py):
  small keyboard-only widget app with a form and confirm dialog.
- [examples/tui/44_widgets_small_controls.py](../../../examples/tui/44_widgets_small_controls.py):
  compact status, details, progress, and toolbar composition.
- [examples/tui/45_widgets_light_controls.py](../../../examples/tui/45_widgets_light_controls.py):
  light menu, tabs, and spinner composition.
