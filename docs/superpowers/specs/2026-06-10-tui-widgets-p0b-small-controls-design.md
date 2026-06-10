# TUI Widgets P0B Small Controls Design

## Status

Draft for spec review.

## Context

`loushang.tui` now has a stable P0A widget foundation:

- Form-oriented controls: `Button`, `Checkbox`, `Toggle`, `RadioGroup`,
  `TextField`, and `SelectList`.
- Composition controls: `Form`, `Dialog`, and `ConfirmDialog`.
- Hardening coverage for theme tokens, render constraints, and
  `Dialog` + `Form` + `SurfaceHost` modal routing.

The next useful gap is not a complex data grid or overlay system. Product
surfaces still need small reusable parts for dense status displays, property
summaries, progress rows, and compact action bars. Today those are still
hand-built from `RenderLine` strings or ad hoc application code.

P0B should add a small display/action batch that stays inside the current
`Renderable` and `Focusable` contracts. It should build on the P0A theme,
constraint, and callback conventions instead of introducing a new layout engine.

## Goals

- Add a focused P0B batch of small controls:
  - `Badge`
  - `StatusPill`
  - `ProgressBar`
  - `KeyValueList`
  - `Toolbar`
- Keep these controls deterministic terminal-pure renderables.
- Reuse existing theme helpers and width helpers.
- Make controls safe under narrow width and short height constraints.
- Keep APIs dataclass-oriented and callback-friendly.
- Make `Toolbar` a local focus scope only; do not introduce global focus
  management.
- Document the new public widgets and their theme tokens.
- Add focused tests for rendering, input handling, theme behavior, and export
  compatibility.

## Non-Goals

- Do not add `Menu`, `Popover`, `PromptDialog`, `Tabs`, `Table`, `TreeView`,
  `Toast`, `TextArea`, or virtualization in this slice.
- Do not add a retained layout engine, CSS layer, global focus manager, or mouse
  pointer capture.
- Do not replace existing `Rule`, `Loader`, `CancellableLoader`, `Text`,
  `TruncatedText`, `Button`, or `Dialog` components.
- Do not add animation scheduling. `ProgressBar` is a static progress
  renderable; activity indication remains the role of `Loader`.
- Do not add new global `InputIntentKind` values for small controls. Use
  callbacks and ordinary consumed-input return values.
- Do not move product-specific status semantics into core `loushang.tui`.

## Control Catalog

| Control | Purpose | Interactivity |
| --- | --- | --- |
| `Badge` | Compact label or count, such as `beta`, `3`, `cached`. | None |
| `StatusPill` | Semantic status label, such as `ready`, `warning`, `failed`. | None |
| `ProgressBar` | Static progress indicator with optional label. | None |
| `KeyValueList` | Dense detail list for labels and values. | None |
| `Toolbar` | Horizontal action group. | Local focus + activation |

This batch intentionally favors small controls that compose into existing forms,
dialogs, status panels, and extension surfaces.

## Public API Shape

New controls should live under `src/loushang/tui/ui_parts/widgets/`:

- `widgets/display.py`
- `widgets/toolbar.py`

Stable classes should be re-exported from:

- `loushang.tui.ui_parts.widgets`
- `loushang.tui.ui_parts`
- top-level `loushang.tui`

Suggested API:

```python
Badge("beta", kind="info")
StatusPill("ready", status="success")
ProgressBar(value=42, total=100, label="Indexing")
KeyValueList([("Model", "Kimi"), ("Mode", "safe")])
Toolbar([ToolbarAction("Save", on_press=save), ToolbarAction("Cancel", on_press=cancel)])
```

All constructor parameters should be keyword-friendly. Required positional
arguments are acceptable only for the primary content field, such as
`Badge("beta")` and `ToolbarAction("Save")`.

## Shared Contracts

All P0B controls must follow the existing widget contracts:

- `render(constraints)` returns `RenderResult`.
- Rendered lines never exceed `constraints.width` after stripping control
  sequences.
- Rendered line count never exceeds `constraints.max_height`.
- Controls do not write to stdout, move hardware cursor, clear rows, or schedule
  timers.
- Theme styling must use existing helpers so ANSI reset behavior and visible
  width semantics match P0A widgets.
- If no `ThemeResolver` is provided, rendering remains plain ASCII.
- Text truncates deterministically rather than overflowing.
- Public docs should mark these as P0B small controls, not complex layout
  primitives.

## Theme Tokens

P0B should extend the existing widget token namespace:

| Token | Applies to |
| --- | --- |
| `widget.badge.default` | Default badge. |
| `widget.badge.info` | Informational badge. |
| `widget.badge.success` | Successful badge. |
| `widget.badge.warning` | Warning badge. |
| `widget.badge.danger` | Dangerous or failed badge. |
| `widget.status.neutral` | Neutral status pill. |
| `widget.status.info` | Informational status pill. |
| `widget.status.success` | Successful status pill. |
| `widget.status.warning` | Warning status pill. |
| `widget.status.danger` | Dangerous or failed status pill. |
| `widget.progress.track` | Progress bar unfilled track. |
| `widget.progress.fill` | Progress bar filled region. |
| `widget.progress.label` | Progress label and numeric text. |
| `widget.keyValue.key` | Key column in `KeyValueList`. |
| `widget.keyValue.value` | Value column in `KeyValueList`. |
| `widget.toolbar.action` | Enabled toolbar actions. |
| `widget.toolbar.focus` | Focused toolbar action. |
| `widget.toolbar.disabled` | Disabled toolbar actions. |

Theme application must preserve visible width. For `ProgressBar`, fill and
track styling may apply to different text segments in the same line, but the
stripped text must still fit the declared width.

## Control Details

### Badge

`Badge` renders a compact one-line label:

```python
Badge(label: str, kind: BadgeKind = "default", theme: ThemeResolver | None = None)
```

Kinds should be `default`, `info`, `success`, `warning`, and `danger`.

Default plain rendering should be ASCII-first, for example `[beta]`. This keeps
the control readable without theme support. The implementation may truncate the
label inside brackets when width is narrow, but it must not exceed the width.

### StatusPill

`StatusPill` renders a semantic status label:

```python
StatusPill(label: str, status: StatusKind = "neutral", theme: ThemeResolver | None = None)
```

Statuses should be `neutral`, `info`, `success`, `warning`, and `danger`.

Default plain rendering should remain ASCII-first, for example `(ready)`. It is
visually distinct from `Badge` so applications can use badges for metadata and
status pills for state.

### ProgressBar

`ProgressBar` renders one line:

```python
ProgressBar(
    value: float,
    total: float = 100,
    label: str = "",
    width: int | None = None,
    show_percent: bool = True,
    theme: ThemeResolver | None = None,
)
```

Rules:

- `ratio = clamp(value / total, 0.0, 1.0)`.
- If `total <= 0`, ratio is `0.0`.
- If `width` is set, bar width is bounded by `constraints.width`; otherwise it
  fills the available row after label/percentage text.
- Default plain bar uses ASCII, such as `[####------] 40%` or
  `Indexing [####------] 40%`.
- The control does not animate and does not schedule invalidation.
- The rendered line must remain useful at narrow widths by truncating label
  first and shrinking the bar before dropping percentage text.

### KeyValueList

`KeyValueList` renders dense label/value rows:

```python
KeyValueList(
    items: Sequence[KeyValueItem | tuple[str, object]],
    separator: str = ": ",
    key_width: int | None = None,
    theme: ThemeResolver | None = None,
)
```

`KeyValueItem` should be a frozen dataclass:

```python
KeyValueItem(key: str, value: object, description: str = "")
```

Rules:

- One item renders per row.
- Values are stringified with `str(value)`.
- `key_width=None` auto-sizes to the longest visible key that fits the current
  width.
- Long keys and values truncate deterministically.
- `description` may be appended after the value when width allows; it should not
  wrap in P0B.
- Height budget truncates the list without scroll state.

### Toolbar

`Toolbar` is a compact horizontal focus scope for actions:

```python
Toolbar(
    actions: Sequence[ToolbarAction],
    active_index: int = 0,
    wrap: bool = True,
    theme: ThemeResolver | None = None,
)
```

`ToolbarAction` should be a frozen dataclass:

```python
ToolbarAction(
    label: str,
    on_press: Callable[[], object] | None = None,
    disabled: bool = False,
    icon: str = "",
    value: str = "",
)
```

Input rules:

- `left` / `right` move active action, skipping disabled actions.
- `home` / `end` jump to first/last enabled action.
- `enter` and `space` activate the active enabled action.
- Activation returns the callback result, or `True` if consumed and callback
  returns `None`.
- If an action has no callback but has `value`, activation returns `value`.
- Disabled actions render visibly disabled and never activate.
- `Toolbar` returns `None` for unhandled input.
- If `actions` is empty, navigation and activation return `None` and rendering
  returns no lines.
- If all actions are disabled, navigation and activation return `None`; the
  toolbar may still render the disabled actions.
- With `wrap=True`, left/right navigation wraps around the enabled actions.
- With `wrap=False`, left/right navigation at the first or last enabled action
  returns `False` to indicate the key was handled but focus did not move.
- `home` and `end` return `False` when at least one action is enabled but the
  active action is already at the requested boundary. They return `None` when
  there is no enabled action.

Rendering rules:

- Render as one line, for example `> [Save]  [Cancel]`.
- Focus indicator must not cause the toolbar line to exceed width.
- If the toolbar is too narrow, truncate at the rendered-line level. P0B does
  not need horizontal scrolling.
- `Toolbar.focus()` and `Toolbar.blur()` control whether the active action shows
  a focused state. This is local focus only; it does not create a global focus
  manager.

## Documentation And Examples

Update:

- `docs/en/reference/tui-widgets.md`
- `docs/zh-CN/reference/tui-widgets.md`

Add an example:

- `examples/tui/44_widgets_small_controls.py`

The example should demonstrate a small status/details surface:

- status pills and badges in a header row
- a progress bar
- a key/value details list
- a toolbar with two actions

The example should be importable in tests. It does not need to run a full
terminal session beyond the existing example pattern.

## Testing Strategy

Add `tests/tui/test_widgets_small_controls.py`.

Tests should cover:

- Public re-exports from `loushang.tui`, `loushang.tui.ui_parts`, and
  `loushang.tui.ui_parts.widgets`.
- `Badge` and `StatusPill` plain rendering, theme token application, and narrow
  width truncation.
- `ProgressBar` ratio clamping, zero/negative total behavior, label/percentage
  rendering, theme segment application, and narrow width compliance.
- `KeyValueList` tuple and `KeyValueItem` input, key auto-width, height
  truncation, description truncation, and theme tokens.
- `Toolbar` focus/blur, navigation, disabled-action skipping, callback result
  semantics, value fallback, activation from key-space and printable-space, and
  width compliance.
- Importing `examples/tui/44_widgets_small_controls.py`.

Broader verification should include:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/44_widgets_small_controls.py docs
```

## Rollout Plan

Implementation should be one small PR with focused commits:

1. Add display-control tests for `Badge`, `StatusPill`, `ProgressBar`, and
   `KeyValueList`.
2. Implement `widgets/display.py` and public exports.
3. Add toolbar tests.
4. Implement `widgets/toolbar.py` and public exports.
5. Add example and docs.
6. Run focused tests, full TUI tests, and Ruff.

Each production change should follow TDD: write failing tests first, verify the
failure, implement the smallest passing change, then run adjacent tests.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Small controls duplicate existing `Text`, `Rule`, or `Loader`. | Keep P0B widgets focused on semantic reusable controls; keep animation with `Loader`. |
| `Toolbar` grows into a general focus manager. | Limit traversal to the toolbar's own actions and expose no global focus registry. |
| Progress rendering becomes too clever under narrow widths. | Define a deterministic fallback order: truncate label, shrink bar, then drop percent if needed. |
| Theme tokens become too broad. | Keep token names under `widget.*` and only document tokens used by P0B controls. |
| `KeyValueList` turns into `Table`. | One item per row, no sorting, no headers, no scroll state, no column virtualization. |

## Success Criteria

- Users can compose a status/details panel with badge, status, progress, key
  values, and toolbar actions without hand-writing render classes.
- All P0B controls obey `RenderConstraints` under narrow and short budgets.
- Theme tokens apply without changing visible width.
- `Toolbar` supports keyboard-only local action selection and activation.
- No P1 data controls or overlay controls are introduced.
- Existing P0A widget tests continue to pass.
- `tests/tui` and Ruff pass after implementation.
