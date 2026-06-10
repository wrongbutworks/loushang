# TUI Widgets P0A Hardening Design

## Status

Draft for spec review.

## Context

PR #145 added the first reusable `loushang.tui` widget batch:

- `Button` / `IconButton`
- `Checkbox`
- `Toggle`
- `RadioGroup`
- `TextField`
- `SelectList`
- `Form` / `FormRow`
- `Dialog` / `ConfirmDialog`

The foundation is intentionally small and compatible with the existing
`Renderable`, `Focusable`, `EditorInputTargetProvider`, `SurfaceHost`, and
`TextInput` contracts. The current tests cover public exports, basic activation,
local form focus, editor target delegation, select-list escape behavior, and
confirm/cancel intent shape.

The remaining risk is not missing catalog breadth. It is contract drift in the
widgets that already exist. The foundation design promised width and height
compliance, theme-token support, visible disabled/error states, and modal
integration through `SurfaceHost`. Those promises should be converted into
focused regression tests before adding P0B controls such as toolbar, menu,
progress, badges, or status pills.

## Goals

- Harden the existing P0A widget batch without expanding the widget catalog.
- Add regression tests for `RenderConstraints` compliance on narrow and short
  renders.
- Apply theme tokens consistently where widgets already expose `theme` or
  `theme_token` parameters, and add narrow optional theme parameters to
  `Form`/`Dialog` where this is required for documented P0A states.
- Ensure themed output keeps the same visible width as unthemed output.
- Make disabled, focused, help, error, selected, and action states visibly
  stable and testable.
- Add `Dialog` + `Form` + `SurfaceHost` modal routing tests using the dialog as
  the surface `focus_target`.
- Preserve current public class names, callback semantics, intent kinds, and
  input routing contracts.

## Non-Goals

- Do not add P0B or P1 controls in this slice.
- Do not introduce a layout engine, retained tree, CSS layer, or global focus
  manager.
- Do not replace `TextInput`, `SelectionSurface`, `DialogSurface`, or
  `SurfaceHost`.
- Do not add product-specific coding-session behavior to core `loushang.tui`
  widgets.
- Do not add new global `InputIntentKind` values unless a failing integration
  test proves the existing intent vocabulary cannot express the behavior.
- Do not redesign visual styling. This slice should make the current ASCII-first
  rendering deterministic and theme-aware.

## Design

### Theme Resolution

Widgets that already accept `ThemeResolver` should resolve and apply structured
theme tokens during rendering. `Form`, `Dialog`, and `ConfirmDialog` may gain
backward-compatible optional `theme: ThemeResolver | None = None` fields because
they render form errors, dialog titles, and dialog actions. Theme application
must use the existing `apply_theme_style()` helper so ANSI reset behavior
matches the rest of the TUI.

The first hardening pass should keep token names simple and local:

| Widget area | Token |
| --- | --- |
| Focus indicator or focused row | `widget.focus` |
| Disabled control text | `widget.disabled` |
| Field or form error text | `widget.error` |
| Field label | `widget.field.label` |
| Field help text | `widget.field.help` |
| Button default kind | `widget.button.default` |
| Button primary kind | `widget.button.primary` |
| Button danger kind | `widget.button.danger` |
| Button ghost kind | `widget.button.ghost` |
| Dialog title | `widget.dialog.title` |
| Dialog actions | `widget.dialog.action` |

State precedence is explicit so tests do not encode accidental behavior:

1. Base style comes from the kind-derived token, such as
   `widget.button.primary`.
2. For `Button`, `theme_token` is a base-style override and replaces the
   kind-derived token when set.
3. Focus style from `widget.focus` is merged over the base style for focused
   enabled controls.
4. Disabled style from `widget.disabled` wins over focus and base styles.
5. Error style from `widget.error` wins for field and form error lines.

When multiple resolved styles are merged, later styles override earlier styles
for the same style keys. If no theme is provided, rendering stays unchanged.

`SelectList` should continue delegating theme behavior to `SelectionSurface`
rather than duplicating selection styling.

### Constraint Compliance

Every P0A widget render path must obey:

- No rendered line exceeds `constraints.width` after stripping control
  sequences.
- No render returns more than `constraints.max_height` lines.
- The smallest valid constraints, `width=1` and `max_height=1`, remain safe and
  deterministic. Non-positive constraints are out of scope because
  `RenderConstraints` already rejects them during construction.
- Focus and disabled state changes do not alter visible width for the same
  content and constraints.
- Cursor declarations are emitted only by editable widgets, and `TextField`
  cursor rows remain correct when label/help/error lines are present or
  truncated by height.

The hardening implementation should prefer tests first. If a widget already
passes, no production code should change.

### State Rendering

Disabled controls currently ignore activation input. This slice should also
make their rendered disabled state themeable. The underlying ASCII text should
stay stable so non-ANSI tests can still assert intent:

- `Button`: same bracketed label, themed by disabled or kind token.
- `Checkbox`: same `[x]` / `[ ]` marker, themed by disabled token.
- `Toggle`: same `[on ]` / `[off]` marker, themed by disabled token.
- `RadioGroup`: disabled options render with the disabled token while active and
  selected indicators remain textual.

`TextField` should prefer `error` over `help_text`, as it does today, and should
make both states themeable. `Form.validate()` currently stores row errors on
`FormRow.error`; those rendered form errors should use the same `widget.error`
token as field-level errors.

### Modal Integration

The foundation documentation says modal dialogs should be opened with the dialog
itself as the `Surface.focus_target`:

```python
dialog = ConfirmDialog(title="Apply changes?", body=form)
host.open_surface(Surface(renderable=dialog, focus_target=dialog, presentation="modal"))
```

This slice should add integration tests that prove:

- Opening the modal focuses the dialog and the dialog focuses its nested form
  body.
- `SurfaceHost.current_editor_target()` returns the active `TextField` target
  while body focus is active.
- Text input routed through the editor target mutates the nested field.
- `tab` can move from the last form field to dialog actions.
- Confirm returns `dialog_confirm` followed by `surface_close`, and
  `SurfaceHost` closes the modal because `surface_close` is in the default close
  list.
- `escape` returns `dialog_cancel` and closes the modal before a nested
  `TextField` can consume escape.

This should remain a routing test, not a new modal framework.

## Files In Scope

Likely implementation files:

- `src/loushang/tui/ui_parts/widgets/_utils.py`
- `src/loushang/tui/ui_parts/widgets/button.py`
- `src/loushang/tui/ui_parts/widgets/choice.py`
- `src/loushang/tui/ui_parts/widgets/field.py`
- `src/loushang/tui/ui_parts/widgets/form.py`
- `src/loushang/tui/ui_parts/widgets/dialog.py`

Allowed public API additions are limited to optional theme plumbing for existing
widgets:

- `Form(theme: ThemeResolver | None = None)` for `FormRow.error` rendering.
- `Dialog(theme: ThemeResolver | None = None)` for title and action rendering.
- `ConfirmDialog` inherits the dialog theme field.

No required constructor parameters or callback signatures may change.

Likely test files:

- `tests/tui/test_widgets_foundation.py`
- a new `tests/tui/test_widgets_hardening.py` if the test set becomes easier to
  scan as a separate file
- `tests/tui/test_basic_theme_compliance.py` only if shared theme assertions
  belong beside existing theme tests

Likely docs:

- `docs/en/reference/tui-widgets.md`
- `docs/zh-CN/reference/tui-widgets.md`

Docs should be updated only where the hardening changes user-facing behavior,
for example documenting widget theme tokens. No broad documentation rewrite is
needed.

## Testing Strategy

Use TDD for the implementation slice:

1. Add focused failing tests for theme application and visible-width stability.
2. Add focused failing tests for narrow and short `RenderConstraints`.
3. Add focused failing tests for `TextField` help/error priority and cursor row
   stability.
4. Add focused failing tests for `Dialog` + `Form` + `SurfaceHost` modal
   integration.
5. Implement the smallest changes needed to pass those tests.
6. Run adjacent widget/theme/surface tests.
7. Run the full TUI suite and Ruff on the touched TUI files.

Expected verification commands:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_basic_theme_compliance.py tests/tui/test_surfaces.py tests/tui/test_input_routing.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui docs
```

If the hardening tests stay inside `test_widgets_foundation.py`, omit
`test_widgets_hardening.py` from the first command.

## Rollout Plan

This should be one small PR with cohesive commits:

1. Add hardening tests for constraints and theme behavior.
2. Apply shared widget theme helpers and fix only failing render paths.
3. Add modal integration tests and fix only failing routing behavior.
4. Update widget reference docs if theme-token behavior becomes user-facing.
5. Run focused checks, then full TUI checks.

The PR should not include new catalog controls. If implementation discovers a
larger design problem, stop and write a follow-up spec instead of expanding this
slice.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Theme tokens create a hidden styling API too early. | Use obvious token names already proposed by the foundation design and document them as initial stable tokens only for existing widgets. |
| ANSI styling breaks width calculations. | Assert both raw ANSI presence and stripped visible width in tests. |
| Hardening turns into a visual redesign. | Keep underlying ASCII text and existing layout unchanged unless a constraint test fails. |
| Modal integration tests become brittle by overchecking internals. | Assert public `SurfaceHost` routing results, focus flags, editor target behavior, and emitted intents instead of private fields. |
| Production changes touch too many modules. | Put shared styling helpers in `widgets/_utils.py` and keep each widget change narrow. |

## Success Criteria

- Existing P0A widgets render within width and height budgets across narrow and
  short constraints.
- Theme tokens apply to focused, disabled, field help/error, button kind, form
  error, and dialog title/action states without changing visible width.
- `TextField` keeps editor behavior delegated to `TextInput` while rendering
  help and error states predictably.
- `Dialog` + `Form` works as a real modal `SurfaceHost` focus target with editor
  routing, tab-to-actions, confirm-close, and cancel-close behavior covered by
  tests.
- No P0B/P1 widgets or unrelated framework abstractions are introduced.
- `tests/tui` and Ruff pass after implementation.
