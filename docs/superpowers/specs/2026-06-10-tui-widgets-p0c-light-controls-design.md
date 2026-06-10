# TUI Widgets P0C Light Controls Design

## Status

Draft for spec review.

## Context

`loushang.tui` now has a practical widget base:

- P0A form and modal controls: `Button`, `IconButton`, `Checkbox`, `Toggle`,
  `RadioGroup`, `TextField`, `SelectList`, `Form`, `Dialog`, and
  `ConfirmDialog`.
- P0B small display and action controls: `Badge`, `StatusPill`,
  `ProgressBar`, `KeyValueList`, and `Toolbar`.
- Shared conventions for render constraints, theme tokens, local focus,
  callback return values, disabled states, and importable examples.

The remaining planned catalog still contains both light controls and heavy
controls:

- Light controls: `Menu`, `Spinner`, `Tabs`.
- Overlay/lifecycle controls: `Popover`, `PromptDialog`, `Toast`.
- Heavy data/editing controls: `Table`, `TreeView`, `TextArea`.

The next slice should keep momentum in the reusable widget catalog without
opening overlay lifecycle or viewport virtualization problems. `Menu`, `Tabs`,
and `Spinner` are the best fit: they are common, compose well with existing
dialogs and surfaces, and can stay within the current `Renderable` /
`Focusable` contracts.

## Goals

- Add a focused P0C light-control batch:
  - `Menu` / `MenuItem`
  - `Tabs` / `TabItem`
  - `Spinner`
- Keep controls terminal-pure and deterministic.
- Reuse the existing width helpers, `RenderResult`, `ThemeResolver`, and
  callback-result helpers.
- Preserve local focus only; do not add global focus management.
- Make controls safe under narrow widths and short heights.
- Keep APIs dataclass-oriented and public through the same three export layers:
  `loushang.tui.ui_parts.widgets`, `loushang.tui.ui_parts`, and top-level
  `loushang.tui`.
- Update docs and examples so implemented controls are no longer listed as
  planned catalog entries.

## Non-Goals

- Do not add `Popover`, `Toast`, `Table`, `TreeView`, `TextArea`, or
  `PromptDialog` in this slice.
- Do not add command-palette filtering, nested submenus, typeahead search, or
  fuzzy matching to `Menu`.
- Do not make `Tabs` own page content, layout regions, lazy rendering, or
  route management.
- Do not make `Spinner` schedule animation frames, start background tasks, or
  depend on `RenderScheduler`.
- Do not add mouse support, pointer capture, or scroll-wheel behavior.
- Do not add new global `InputIntentKind` values for these controls.
- Do not introduce a layout engine, CSS layer, or terminal drawing side effects.

## Approach

Recommended approach: add three small, independent modules:

- `widgets/menu.py`
- `widgets/tabs.py`
- `widgets/spinner.py`

This keeps each state machine small and avoids growing `display.py` or
`toolbar.py` into mixed-responsibility modules. The controls share conventions,
not inheritance.

Rejected alternatives:

| Alternative | Reason not chosen |
| --- | --- |
| Build `Menu` on top of `SelectionSurface`. | `SelectionSurface` is optimized for selectable values, while `Menu` needs action callbacks, disabled skipping, and explicit activation results. |
| Combine `Menu` and `Tabs` into one generic roving-focus list. | Their semantics differ: menu navigation is explicit activation; tabs switch selected views during navigation. A generic abstraction would obscure those contracts. |
| Implement overlay controls first. | `Popover` and `Toast` need surface lifecycle decisions. They are useful, but higher risk than this light-control batch. |
| Start with `Table` / `TreeView` / `TextArea`. | Those need scrolling, selection, editing, and likely virtualization. They should be designed after the light catalog is stable. |

## Shared Contracts

All P0C controls must follow the existing widget contracts:

- `render(constraints)` returns `RenderResult`.
- Rendered line count never exceeds `constraints.max_height`.
- Visible line width never exceeds `constraints.width` after stripping ANSI
  control sequences.
- Controls do not write to stdout, clear rows, move the hardware cursor, or
  schedule timers.
- If no `ThemeResolver` is provided, rendering remains plain ASCII.
- `Menu`, `Tabs`, and `Spinner` all accept `ThemeResolver | None`.
- Theme application must preserve visible width.
- Disabled entries render visibly disabled and ignore activation.
- Empty/all-disabled controls return `None` for navigation and activation.
- Non-editor activation accepts both `InputEvent(kind="key", key="space")` and
  `InputEvent(kind="text", text=" ")`.
- Callback results follow P0A/P0B behavior: callback return value is returned;
  callback returning `None` becomes `True`.

## Theme Tokens

P0C should extend the existing `widget.*` namespace:

| Token | Applies to |
| --- | --- |
| `widget.menu.item` | Enabled inactive menu items. |
| `widget.menu.focus` | Focused active menu item. |
| `widget.menu.disabled` | Disabled menu items. |
| `widget.menu.description` | Menu item descriptions when width permits. |
| `widget.tabs.tab` | Enabled unselected tabs. |
| `widget.tabs.selected` | Selected tab when the tab strip is not focused. |
| `widget.tabs.focus` | Selected tab while the tab strip is focused. |
| `widget.tabs.disabled` | Disabled tabs. |
| `widget.spinner.frame` | Spinner frame glyph. |
| `widget.spinner.label` | Spinner label text. |

## Public API Shape

Suggested usage:

```python
Menu(
    [
        MenuItem("open", "Open"),
        MenuItem("delete", "Delete", disabled=True),
        MenuItem("quit", "Quit", on_select=lambda: "quit"),
    ]
)

Tabs(
    [
        TabItem("overview", "Overview"),
        TabItem("logs", "Logs"),
    ],
    value="overview",
)

Spinner(label="Loading", frame=3)
```

## Control Details

### Menu

`Menu` is a short vertical action list. It is not a command palette and does not
filter, search, nest, or own overlay closing behavior.

Suggested API:

```python
@dataclass(frozen=True, slots=True)
class MenuItem:
    value: str
    label: str
    description: str = ""
    disabled: bool = False
    icon: str = ""
    on_select: Callable[[], object] | None = None


@dataclass(slots=True)
class Menu:
    items: Sequence[MenuItem]
    active_index: int = 0
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
```

Behavior:

- `focus()` and `blur()` toggle local focus.
- `active_value` returns the active enabled item value, or `""` if there is no
  active enabled item.
- `up` / `down` move the active item and skip disabled items.
- `home` / `end` jump to the first/last enabled item.
- `enter` / `space` activate the active item.
- `__post_init__` normalizes `active_index` to an enabled item:
  - Clamp the requested index into the item range.
  - Keep it if that item is enabled.
  - Otherwise choose the next enabled item after the clamped index.
  - If no later item is enabled, choose the first enabled item.
  - If no item is enabled, keep `0`.
- Activation returns `on_select()` result when provided, `item.value` when no
  callback exists, or `True` only when the callback returned `None`.
- `wrap=False` boundary movement returns `False`.
- `home` / `end` return `False` when at least one enabled item exists but the
  active item is already at the requested boundary.
- One-enabled-item menus return `False` for movement that cannot change the
  active item.
- Empty/all-disabled menus return `None` for movement and activation.

Rendering:

- One item renders per row.
- Focused active row uses `> ` prefix.
- Non-focused rows use a stable two-space prefix so focus changes do not resize
  the menu.
- The label may include `icon` as a plain text prefix.
- `description` may be appended as `  {description}` only when the full
  separator plus at least one description column fits after the rendered label.
  If it does not fit, omit the description rather than truncating the label to
  make room. When appended, truncate the description to the remaining row
  width. Descriptions never wrap in P0C.
- If the active item is outside the current height window, rendering adjusts a
  minimal `_first_visible_index` so the active item is visible. This is not
  table virtualization; it is only enough to keep keyboard navigation visible.

### Tabs

`Tabs` is a horizontal selected-value control. It does not own page content. The
parent renderable reads `tabs.value` and decides which body to render.

Suggested API:

```python
@dataclass(frozen=True, slots=True)
class TabItem:
    value: str
    label: str
    disabled: bool = False
    badge: str = ""


@dataclass(slots=True)
class Tabs:
    tabs: Sequence[TabItem]
    value: str = ""
    wrap: bool = True
    on_change: Callable[[str], object] | None = None
    theme: ThemeResolver | None = None
    focused: bool = False
```

Behavior:

- `focus()` and `blur()` toggle local focus.
- `__post_init__` normalizes `value` to a canonical enabled tab value:
  - Keep the requested value if it matches an enabled tab.
  - If the requested value matches a disabled tab, choose the next enabled tab
    after that disabled tab.
  - If no later tab is enabled after a disabled requested tab, choose the first
    enabled tab.
  - Otherwise choose the first enabled tab.
  - If no tab is enabled, set `value` to `""`.
  - Initialization normalization does not call `on_change`.
- `selected_value` returns the canonical `value`.
- `left` / `right` move selection and skip disabled tabs.
- `home` / `end` jump to the first/last enabled tab.
- Movement changes `value` immediately because tabs represent view switching.
- If movement changes `value`, `on_change(value)` is called and its callback
  result is returned. Without a callback, movement returns `True`.
- Boundary movement with `wrap=False` returns `False`.
- `home` / `end` return `False` when at least one enabled tab exists but the
  selected tab is already at the requested boundary.
- One-enabled-tab strips return `False` for movement that cannot change
  selection.
- Empty/all-disabled tab strips return `None` for movement.
- `enter` / `space` return the current selected value, or `None` if there is no
  enabled tab. They do not call `on_change` unless the value changes.

Rendering:

- Renders one horizontal row.
- Every tab segment reserves a stable two-character state prefix:
  - `> ` for focused selected tab.
  - `* ` for selected tab while not focused.
  - `  ` for unselected tabs.
- Labels render as `[Label]`.
- `badge` may append inside the segment, for example `[Logs 3]`.
- Long rows truncate to the render width; P0C does not horizontally scroll tab
  strips.

### Spinner

`Spinner` is a display-only activity indicator. It is deliberately static from
the control's perspective: the caller passes `frame`, and the caller or runtime
decides when to request another render.

Suggested API:

```python
@dataclass(slots=True)
class Spinner:
    label: str = ""
    frame: int = 0
    frames: Sequence[str] = ("|", "/", "-", "\\")
    theme: ThemeResolver | None = None
```

Behavior:

- `render()` emits at most one line.
- The frame glyph is `frames[frame % len(frames)]`.
- Empty `frames` render the label only.
- The control has no `handle_input()`, no `focus()`, and no scheduling.

Rendering:

- Default plain text is ASCII-first, such as `| Loading`.
- If `label` is empty, only the frame glyph renders.
- If `frames` is empty, only the label renders.
- If both `label` and `frames` are empty, render one empty line. This preserves
  one-line display-control behavior while still respecting `max_height`.
- Narrow widths truncate deterministically without overflowing.

## File Structure

- Create `src/loushang/tui/ui_parts/widgets/menu.py`.
- Create `src/loushang/tui/ui_parts/widgets/tabs.py`.
- Create `src/loushang/tui/ui_parts/widgets/spinner.py`.
- Modify `src/loushang/tui/ui_parts/widgets/__init__.py`.
- Modify `src/loushang/tui/ui_parts/__init__.py`.
- Modify `src/loushang/tui/__init__.py`.
- Create `tests/tui/test_widgets_light_controls.py`.
- Create `examples/tui/45_widgets_light_controls.py`.
- Update `docs/en/reference/tui-widgets.md`.
- Update `docs/zh-CN/reference/tui-widgets.md`.

## Testing Strategy

Focused tests should cover:

- Public re-exports through all three public layers.
- `Menu` rendering, disabled skipping, initial disabled/out-of-range
  `active_index` normalization, callback return values, `wrap=False`
  boundaries, `home`/`end` and one-enabled-item no-op returns,
  empty/all-disabled semantics, height-window active visibility, both key-space
  and printable-space activation, description rendering thresholds, and width
  constraints.
- `Tabs` rendering, immediate selection on navigation, `on_change` results,
  initialization normalization for default/invalid/disabled values without
  calling `on_change`, disabled skipping, `wrap=False` boundaries, `home`/`end`
  and one-enabled-tab no-op returns, activation return values, both key-space
  and printable-space activation, and width constraints.
- `Spinner` frame modulo behavior, empty frames, label-only rendering, theme
  tokens, both-empty rendering, and width constraints.
- Theme tokens do not change visible width.
- The example file imports with `runpy.run_path()`.

Regression suites:

- Run the new focused test file.
- Run existing P0A/P0B widget tests:
  - `tests/tui/test_widgets_foundation.py`
  - `tests/tui/test_widgets_hardening.py`
  - `tests/tui/test_widgets_small_controls.py`
- Run full `tests/tui`.
- Run Ruff over `src/loushang/tui`, `tests/tui`, docs, and the new example.

## Documentation Requirements

English and Chinese widget reference docs should:

- Add a P0C light-controls section.
- Add `Menu`, `Tabs`, and `Spinner` rows.
- Add P0C theme tokens.
- Add a link to `examples/tui/45_widgets_light_controls.py`.
- Remove `Menu`, `Spinner`, and `Tabs` from the planned catalog.

The planned catalog should still include `Popover`, `PromptDialog`, `Table`,
`TreeView`, `Toast`, and `TextArea`.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| `Menu` grows into command palette. | Keep P0C menu as a short action list: no filtering, typeahead, nesting, or fuzzy matching. |
| `Tabs` grows into layout/routing. | `Tabs` owns only selected value; parent owns content rendering. |
| `Spinner` implies animation scheduling. | `Spinner` accepts `frame`; scheduler integration remains a caller concern. |
| Navigation semantics diverge from existing controls. | Reuse Toolbar-style boundary and all-disabled return semantics, and document the difference that tabs select during navigation. |
| Theme tokens become too broad. | Use narrowly named `widget.menu.*`, `widget.tabs.*`, and `widget.spinner.*` tokens only. |

## Success Criteria

- `Menu`, `MenuItem`, `Tabs`, `TabItem`, and `Spinner` are stable public
  exports.
- Controls obey width and height constraints in focused tests.
- Theme tokens apply without visible-width growth.
- `Menu` covers navigation, activation, disabled, empty, all-disabled,
  callback, and boundary semantics.
- `Tabs` covers selection, disabled, callback, activation, empty/all-disabled,
  and boundary semantics.
- `Spinner` is explicitly static and caller-driven.
- Docs and examples are updated.
- Full TUI tests and Ruff pass.
