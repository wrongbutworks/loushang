# TUI Widgets Foundation Design

## Status

Draft for implementation planning.

## Context

`loushang.tui` now has the foundation needed for reusable interactive UI parts:

- `RenderLoop` render planning is strategy-based and easier to reason about.
- `SurfaceHost` owns focus restoration and surface routing.
- `InputRouter` can route editing operations to focused editor targets.
- `TextInput` exposes an `EditorInputTargetProvider` adapter for single-line
  editable fields.
- `SelectionSurface`, `DialogSurface`, and `ApprovalSurface` prove the existing
  render/input contracts can support interactive surfaces.

The gap is a reusable control catalog. Product adapters and examples can render
text, status rows, selection lists, dialogs, and text input, but common
application controls such as buttons, checkboxes, radio groups, toggles, forms,
and confirm dialogs still need to be hand-built. This raises the cost of
extension UIs, settings UIs, command palettes, and multi-field workflows.

This slice should turn the current framework primitives into a coherent widget
foundation without becoming a large UI framework rewrite.

## Terminology

- `Renderable`: the framework protocol that renders into `RenderResult`.
- `Focusable`: the framework protocol that receives normalized `InputEvent`
  values.
- `UI Part`: a concrete visible renderable in `src/loushang/tui/ui_parts`.
- `Control`: an interactive UI part. A control is still just a `Renderable`,
  optionally `Focusable`, and optionally an `EditorInputTargetProvider`.
- `Widget`: a public convenience term for controls and small composed UI parts.
  Architecture docs should still prefer `UI Part` and `Control`.

## Goals

- Define a practical control catalog large enough to guide the widget ecosystem.
- Implement a first P0A batch that supports common forms, settings, and dialogs.
- Keep controls deterministic, terminal-pure renderables that never write
  directly to stdout or move the hardware cursor.
- Reuse existing input, focus, selection, theme, and render primitives instead of
  introducing a parallel framework.
- Make controls usable through `Tui`, `SurfaceHost`, extension widgets, and
  product-specific surfaces.
- Preserve current `InputIntentKind` semantics. New P0A controls should prefer
  typed callbacks over expanding global intent kinds.
- Add tests and docs that make the first widget batch safe to extend.

## Non-Goals

- Do not build a Textual-style layout engine, CSS system, or retained virtual
  DOM.
- Do not replace `Composer`, `TextInput`, `SelectionSurface`, or `SurfaceHost`.
- Do not add a global multi-control focus manager in this slice.
- Do not implement `Table`, `TreeView`, `TextArea`, `Toast`, or complex
  viewport virtualization in P0A.
- Do not add mouse drag interactions, pointer capture, or text selection inside
  non-editor controls.
- Do not move product-specific coding-session concepts into `loushang.tui`.
- Do not widen `InputIntentKind` for every control event in the first batch.

## Catalog And Rollout

The design covers a broader catalog, but implementation should land in
incremental batches.

| Batch | Control | Purpose | First implementation |
| --- | --- | --- | --- |
| P0A | `Button` | Pressable action row. | Yes |
| P0A | `IconButton` | Compact symbolic action. | Yes, as a `Button` mode or factory, not necessarily a separate state machine. |
| P0A | `Checkbox` | Binary selection with label. | Yes |
| P0A | `RadioGroup` | Mutually exclusive options. | Yes |
| P0A | `Toggle` | Compact on/off switch. | Yes |
| P0A | `TextField` | Labeled single-line text field. | Yes, wraps `TextInput`. |
| P0A | `SelectList` | Reusable list selection control. | Yes, adapts `SelectionSurface`. |
| P0A | `Form` / `FormRow` | Vertical field composition and validation summary. | Yes |
| P0A | `Dialog` / `ConfirmDialog` | Focusable modal composition and confirmation flow. | Yes |
| P0B | `PromptDialog` | Dialog with one or more fields and actions. | No |
| P0B | `Toolbar` | Horizontal action group. | No |
| P0B | `Menu` | Short action list or nested command list. | No |
| P0B | `Popover` | Anchored transient content. | No |
| P0B | `ProgressBar` / `Spinner` | Task progress and activity indication. | No |
| P0B | `Badge` / `StatusPill` | Small state labels. | No |
| P0B | `KeyValueList` | Dense detail display. | No |
| P1 | `Tabs` | View switching. | No |
| P1 | `Table` | Dense tabular data. | No |
| P1 | `TreeView` | Hierarchical navigation. | No |
| P1 | `Toast` | Non-blocking notifications. | No |
| P1 | `TextArea` | Multi-line field not tied to prompt semantics. | No |

P0A must be enough to build a small settings dialog, search/filter dialog, and
confirmation flow without hand-writing focusable control classes.

## P0A Public API Shape

P0A controls should live under `src/loushang/tui/ui_parts/widgets/` to avoid a
single large module. Public re-exports should be added through
`loushang.tui.ui_parts` and top-level `loushang.tui` only for stable classes.

Suggested files:

- `widgets/button.py`
- `widgets/choice.py`
- `widgets/field.py`
- `widgets/form.py`
- `widgets/dialog.py`
- `widgets/selection.py`
- `widgets/__init__.py`

The API should be dataclass-oriented and callback-friendly:

```python
Button(label="Save", on_press=lambda: "save")
Checkbox(label="Enable cache", checked=True, on_change=handle_checked)
RadioGroup(options=[Choice("fast", "Fast"), Choice("safe", "Safe")])
Toggle(label="Auto approve", value=False)
TextField(label="Name", value="tower")
SelectList(items=[SelectItem("Kimi"), SelectItem("Qwen")])
ConfirmDialog(title="Delete session?", confirm_label="Delete")
```

Callbacks may return an object. `handle_input()` returns that object when the
control consumes an activation event and the callback returns a value. If the
callback returns `None`, the control returns `True` for consumed events. This
matches existing `TextInput` behavior, where consumed input can return `True`
and submit/cancel callbacks can perform side effects.

## Control Contracts

All P0A controls must follow these rules:

- `render(constraints)` returns a `RenderResult` and respects
  `constraints.width` and `constraints.max_height`.
- Controls do not write directly to the terminal, clear rows, move the hardware
  cursor, or schedule timers.
- `handle_input(event)` returns one of:
  - callback result
  - `InputIntent` for existing semantics such as `select`, `dialog_confirm`,
    `dialog_cancel`, or `surface_close`
  - `True` when input was consumed and there is no semantic value
  - `None` when input was not consumed
- Controls with editable text should expose `editor_input_target()` by
  delegating to `TextInput`.
- Disabled controls render visibly disabled and ignore activation input.
- Focused controls render a stable focus indicator and must not change their
  width when focus changes.
- Activation keys use existing keybinding semantics where possible:
  - `enter` confirms a focused button, checkbox, toggle, radio option, or
    selected list item.
  - `space` toggles checkbox/toggle and activates focused buttons when the
    focused control is not an editor.
  - `escape` should only emit cancel/close semantics for dialog-like containers,
    not ordinary controls embedded in a form.
- Non-editor controls should treat both `InputEvent(kind="key", key="space")`
  and `InputEvent(kind="text", text=" ")` as space activation. Editable controls
  keep printable space as text insertion.

## P0A Control Details

### Button

`Button` renders one line and supports label, optional icon text, disabled state,
kind, theme tokens, and `on_press`.

Kinds should start small: `default`, `primary`, `danger`, and `ghost`. They map
to theme tokens, not hard-coded product colors. The first implementation can
render icons as text prefixes; it should not introduce a terminal icon registry.

`IconButton` should be either:

- a lightweight factory around `Button(label="", icon="...")`, or
- a class only if tests prove it needs distinct rendering rules.

The first plan should prefer the factory or mode to keep the API smaller.

### Checkbox

`Checkbox` owns `checked: bool`, `label`, optional `description`, disabled
state, and `on_change`.

It toggles on `enter` and `space`, returns the callback result or `True`, and
exposes `set_checked(value)` for programmatic updates. Rendering should be
ASCII-first, for example `[x] Label` and `[ ] Label`, unless the surrounding
file already uses non-ASCII symbols.

### RadioGroup

`RadioGroup` owns a tuple of `Choice` objects, the selected value, optional
disabled choices, and `on_change`.

It is a single focusable control in P0A, not one focus target per option. Up/down
move the active option, `enter` and `space` commit the active option. Rendering
uses one row per visible option and may truncate descriptions. A later focus
manager can split individual options if needed.

### Toggle

`Toggle` is a compact binary control. It has the same state and callback shape as
`Checkbox`, but renders as an on/off setting row. The first implementation can
reuse checkbox input handling internally while keeping rendering distinct.

### TextField

`TextField` composes a label, optional help/error text, and an inner
`TextInput`. It implements `Focusable` and `EditorInputTargetProvider` by
delegating to the inner field.

`TextField` should not fork editing behavior. All cursor movement, selection,
undo, paste, kill/yank, and submit handling stay in `TextInput`.

### SelectList

`SelectList` adapts the existing `SelectionSurface` into a general control name.
It should expose selected value/item helpers and keep the tested navigation,
search, fuzzy filtering, scroll info, and theme behavior from
`SelectionSurface`.

The first implementation can delegate rendering and navigation to
`SelectionSurface`, but it must not be a plain alias. `SelectionSurface` returns
`InputIntent(kind="surface_close")` on `escape`, which is correct for a popup
surface but wrong for an ordinary control embedded in a form.

`SelectList` therefore has explicit escape behavior:

- `close_on_escape=False` by default. `escape` returns `None` so a parent form or
  dialog can decide whether the dialog should close.
- `close_on_escape=True` returns the underlying `surface_close` intent for
  popup-style uses.

This keeps embedded lists from closing their parent surface unexpectedly while
still allowing popup select lists to reuse the existing close semantics.

### Form And FormRow

`Form` is a vertical composition of controls. It renders rows within the height
budget and can expose helpers for collecting values. It is not a full focus
manager in P0A.

The initial focus model is explicit:

- A `Form` must implement `Focusable` in P0A and track one active child.
- `tab` and `shift+tab` move between focusable children.
- Ordinary input is delegated to the active child.
- `Form` does not open or close surfaces by itself.
- `Form` exposes `focus_next(wrap: bool = True) -> bool` and
  `focus_previous(wrap: bool = True) -> bool`. The return value indicates
  whether focus moved. Dialogs call these with `wrap=False` so focus can leave
  the form and reach dialog actions at the form boundary.

`FormRow` supplies the stable field id:

```python
FormRow(
    field_id="model",
    control=SelectList(...),
    validator=lambda value: "Choose a model" if not value else None,
)
```

Validation is simple and synchronous. A form field may have an error string.
`Form.validate()` calls row validators with the row's current value and returns
a `FormValidationResult` containing errors by `field_id`. Controls can expose
their value through conventional attributes such as `value`, `checked`, or
`selected_value`; rows may also accept an explicit `value_getter` when a control
needs custom extraction. Async validation and cross-field dependency engines are
out of scope.

### Dialog And ConfirmDialog

`Dialog` is a composed renderable for modal surfaces. It owns title, body
renderable or text, optional actions, and cancel behavior. It should be easy to
open through `SurfaceHost.open_surface(Surface(..., presentation="modal"))`.

When a dialog is opened as a modal surface, the dialog itself is the
`Surface.focus_target`:

```python
dialog = ConfirmDialog(...)
host.open_surface(Surface(renderable=dialog, focus_target=dialog, presentation="modal"))
```

Do not set a nested `Form` or `TextField` as the modal surface focus target.
The dialog owns top-level modal focus and may focus a nested child internally.

`ConfirmDialog` is a concrete dialog with confirm and cancel actions. It may
return existing `InputIntent(kind="dialog_confirm")` and
`InputIntent(kind="dialog_cancel")`, matching current `DialogSurface`.

Confirm close behavior is explicit:

- Cancel returns `InputIntent(kind="dialog_cancel")`, which already closes the
  current surface under `SurfaceHost` default `close_on_intents`.
- Confirm defaults to auto-close by returning
  `(InputIntent(kind="dialog_confirm"), InputIntent(kind="surface_close"))`.
  `SurfaceHost` will close the current surface because `surface_close` is in the
  default close list, while callers still receive the confirm intent.
- `ConfirmDialog(close_on_confirm=False)` returns only
  `InputIntent(kind="dialog_confirm")` for workflows that need to keep the
  dialog open after validation or async work.

The current `DialogSurface` should not be removed in P0A. The first
implementation can either delegate `ConfirmDialog` to `DialogSurface` or keep
`DialogSurface` as a compatibility wrapper after tests prove parity.

### Modal Focus Contract

`Dialog` owns top-level focus among:

- an optional body focus target, usually a `Form`
- zero or more action buttons

The dialog handles dialog-level keys before delegating:

- `escape` and `ctrl+c` cancel the dialog before the focused child sees the
  event. This prevents an embedded `TextField` from swallowing modal cancel.
- `tab` and `shift+tab` move between body and action focus. If the body focus
  target is a `Form`, the dialog asks the form to move within its fields using
  `wrap=False`; when the form reports no movement at an edge, the dialog moves
  to the next top-level focus slot.
- `left` and `right` may move between action buttons when an action slot is
  active.
- Other input is delegated to the active body or action focus target.

`Form` remains independently focusable for non-dialog surfaces. In modal form
workflows, however, `Dialog` is the surface focus target and the form is an
internal focus scope. This keeps surface close behavior, text editing, and action
buttons under one modal owner.

## Focus And Input Model

P0A should preserve the current routing hierarchy:

1. `TuiRunner` parses terminal input into `InputEvent`.
2. `Tui` or product input handlers pass events to `SurfaceHost`.
3. `SurfaceHost` routes events to the current focused surface or base focus.
4. Modal surfaces should use the `Dialog` as the surface focus target.
5. `Dialog` handles modal keys, then delegates to a nested `Form` or action.
6. `Form` may delegate events to its active child.
7. Editable children expose editor targets through `EditorInputTargetProvider`.

There is no global tab order across every renderable in this slice. A `Form`
owns local tab traversal only for its direct controls. Cross-surface focus
restoration remains `SurfaceHost` responsibility.

This keeps the first batch compatible with #144 while avoiding a second focus
system.

## Rendering And Layout Rules

Controls should use existing width helpers:

- `visible_width`
- `truncate_to_width`
- `wrap_ansi`
- `autowrap_safe_width`
- `slice_by_column` when cursor or selection mapping needs it

Rules:

- Text must not exceed the render width after stripping ANSI sequences.
- Focus, disabled, selected, and error states must not cause layout width shifts.
- Multi-row controls must respect height budgets and render partial content
  deterministically.
- Descriptions and errors should truncate or wrap based on the control's
  documented behavior; they must not create hidden overflow.
- Controls should return cursor declarations only for editable fields.

## Theming

P0A should use structured theme tokens where practical and keep hard-coded ANSI
fallbacks minimal. Suggested tokens:

- `widget.focus`
- `widget.disabled`
- `widget.error`
- `widget.button.default`
- `widget.button.primary`
- `widget.button.danger`
- `widget.button.ghost`
- `widget.choice.selected`
- `widget.field.label`
- `widget.field.help`
- `widget.dialog.title`
- `widget.dialog.border`

The first implementation does not need a full default theme expansion. It should
accept `ThemeResolver | None` and resolve tokens when provided, matching
existing UI part patterns.

## Documentation And Examples

Add public docs for the first stable batch:

- `docs/en/reference/tui-widgets.md`
- `docs/zh-CN/reference/tui-widgets.md`
- links from the English and Chinese reference indexes
- an example such as `examples/tui/43_widgets_foundation.py`

The example should demonstrate:

- a form with text field, checkbox, radio group, and toggle
- a select list or settings list
- a confirm dialog opened through `Tui` or `SurfaceHost`
- keyboard-only operation

Docs should call out that P1 catalog items are planned, not implemented.

## Testing Strategy

Use focused unit tests first, then one integration example test.

New tests should cover:

- Import and re-export compatibility for P0A classes.
- Button activation, disabled behavior, callback return values, and stable
  focused rendering.
- Checkbox and toggle state changes on `enter` and `space`.
- Radio group navigation, disabled option skipping, selection commit, and
  callback behavior.
- TextField delegation to `TextInput`, including editor target routing and
  cursor declaration.
- SelectList parity with `SelectionSurface` for navigation and selection.
- SelectList escape behavior in embedded mode and popup close mode.
- Form tab traversal, child delegation, validation result shape, and bounded
  rendering.
- ConfirmDialog confirm auto-close, confirm without close, cancel close, and
  returned intent ordering.
- Modal focus routing where `Dialog` is the surface focus target, `escape`
  cancels before an embedded `TextField` sees the event, and tab can leave a
  nested form to reach action buttons.
- Space activation for non-editor controls from key-space and printable-space
  events, without breaking TextField space insertion.
- Theme token application without visible width changes.
- Render width and height compliance for narrow and short constraints.

Broader TUI tests should run after implementation because widget controls touch
public exports and focus routing:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui
```

## Rollout Plan

Implementation planning should split this into small commits:

1. Add widget package skeleton, shared choice/action dataclasses, and public
   exports.
2. Implement `Button`, `Checkbox`, `Toggle`, and `RadioGroup` with tests.
3. Implement `TextField` and `SelectList` wrappers with tests.
4. Implement `Form`, `FormRow`, validation result, and local tab traversal.
5. Implement `Dialog` and `ConfirmDialog`, keeping current surfaces compatible.
6. Add reference docs and the widgets foundation example.
7. Run focused tests, then all `tests/tui`, then ruff on changed TUI files.

Each commit should keep existing TUI tests green.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| The widget layer grows into a second framework. | Keep controls as `Renderable`/`Focusable` UI parts; no layout engine or global focus manager in P0A. |
| P0A duplicates existing `SelectionSurface` or `TextInput` behavior. | Prefer wrappers/delegation and parity tests over copy-paste. |
| New intent kinds leak product-specific semantics into core input. | Use callbacks and existing dialog/select intents only. |
| Form focus collides with `SurfaceHost` focus. | Make `Form` local traversal explicit; `SurfaceHost` still owns surface focus. |
| File size grows quickly. | Use a `widgets/` package with narrow modules from the start. |
| P1 controls are mistaken as implemented. | Docs and exports list only P0A as available; catalog marks later controls as planned. |

## Success Criteria

- A user can build a small keyboard-only modal form with text, boolean choices,
  exclusive choices, a select list, and confirm/cancel actions without defining
  custom focusable classes.
- P0A controls obey `RenderConstraints` and have deterministic headless tests.
- Existing `TextInput`, `SelectionSurface`, `DialogSurface`, and `SurfaceHost`
  behavior remains compatible.
- No new terminal writer paths are introduced outside the runtime.
- Public docs show how to use the first widget batch and clearly mark later
  catalog items as planned.
- `tests/tui` and ruff checks pass after implementation.
