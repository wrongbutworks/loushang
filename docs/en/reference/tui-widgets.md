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

P0A widgets accept `ThemeResolver` where styling is supported. Initial stable
tokens are:

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

## Planned Catalog

`Toolbar`, `Menu`, `Popover`, `ProgressBar`, `Spinner`, `Badge`, `StatusPill`,
`KeyValueList`, `Tabs`, `Table`, `TreeView`, `Toast`, and `TextArea` are planned
catalog entries. They are not part of the P0A implementation.

## Example

- [examples/tui/43_widgets_foundation.py](../../../examples/tui/43_widgets_foundation.py):
  small keyboard-only widget app with a form and confirm dialog.
