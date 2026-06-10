# TUI Widgets P1A Table Design

## Status

Draft for implementation planning.

## Context

`loushang.tui` now has a practical widget foundation:

- P0A form and dialog controls: `Button`, `IconButton`, `Checkbox`,
  `Toggle`, `RadioGroup`, `TextField`, `SelectList`, `Form`, and `Dialog`.
- P0B compact display and action controls: `Badge`, `StatusPill`,
  `ProgressBar`, `KeyValueList`, and `Toolbar`.
- P0C light controls: `Menu`, `Tabs`, and `Spinner`.

These controls are enough for settings panes, modal forms, status panels, and
short action lists. The largest remaining gap is dense list-shaped data. Product
surfaces still need to hand-render session lists, model lists, tool-call
summaries, diagnostics, and test results. A small reusable table control gives
extensions and product UIs a common way to show comparable rows without
introducing a layout engine.

This slice adds the first table widget. It should be intentionally smaller than
a full data-grid: deterministic rendering, local active-row navigation, simple
selection, and strict width/height compliance.

## Goals

- Add a public `Table` widget for dense row/column data.
- Keep `Table` a normal `Renderable` and optional local `Focusable`, consistent
  with existing widgets.
- Support fixed-width columns plus simple remaining-width allocation.
- Support left and right alignment for text cells.
- Support active row navigation with `up`, `down`, `home`, and `end`.
- Support row activation with `enter`, `space` key events, and printable space
  text events.
- Skip disabled rows during navigation and activation.
- Keep the active row visible inside the rendered height window.
- Apply documented theme tokens without changing visible width.
- Export the stable public API from `loushang.tui.ui_parts.widgets`,
  `loushang.tui.ui_parts`, and top-level `loushang.tui`.
- Add focused tests and a small example that demonstrate table composition.

## Non-Goals

- Do not add sorting, filtering, search, column resizing, or column reordering.
- Do not add horizontal scrolling in this slice.
- Do not add row virtualization or a separate viewport abstraction.
- Do not support nested renderable cells. Cell values become text with `str()`.
- Do not add editable cells.
- Do not add mouse interactions.
- Do not introduce a global focus manager, retained widget tree, layout engine,
  or CSS-like style system.
- Do not implement `TextArea`, `PromptDialog`, `TreeView`, `Toast`, or
  `Popover` in this slice.

## Public API

Add `src/loushang/tui/ui_parts/widgets/table.py`.

```python
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

TableAlign = Literal["left", "right"]

@dataclass(frozen=True, slots=True)
class TableColumn:
    key: str
    header: str
    width: int | None = None
    min_width: int = 1
    align: TableAlign = "left"

@dataclass(frozen=True, slots=True)
class TableRow:
    value: str
    cells: Mapping[str, object] | Sequence[object]
    disabled: bool = False
    on_select: Callable[[], object] | None = None

@dataclass(slots=True)
class Table:
    columns: Sequence[TableColumn]
    rows: Sequence[TableRow | Mapping[str, object] | Sequence[object]]
    active_index: int = 0
    show_header: bool = True
    empty_text: str = "No rows"
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
```

`TableRow` is the stable row shape. `Table` may accept plain mappings or
sequences for convenience and normalize them internally:

- A mapping row uses column keys to look up cell values. Its row `value`
  defaults to `str()` of the first available key column value, or `str()` of the
  row index if no useful value exists. `None` and empty string values are not
  useful fallback values.
- A sequence row maps by column order. Its row `value` defaults to the first
  cell converted with `str()`, or `str()` of the row index for an empty
  sequence.
- Callers that need stable semantic activation results should pass `TableRow`.

The first implementation should normalize rows during `__post_init__` into
tuples so render and navigation logic is deterministic.

Column configuration is normalized instead of raising for small invalid values:
`min_width` becomes `max(0, min_width)`, fixed `width` becomes
`max(0, width)`, and `width=None` remains flexible.

## Rendering

`Table.render(constraints)` returns a `RenderResult` whose visible lines always
fit `constraints.width` and `constraints.max_height`.

Layout rules:

- `RenderConstraints` already guarantees positive width and height.
- The effective width is `autowrap_safe_width(constraints.width)`.
- If there are no columns, render `empty_text` as a plain one-line message when
  height allows. It does not reserve the table row prefix because there is no
  cell grid to align with.
- If `show_header=True`, the header consumes the first rendered line.
- Body rows consume the remaining height.
- The active enabled row is kept visible in the body window.
- If there are columns but no rows, render the header if enabled, then
  `empty_text` if height remains. In this case the empty line reserves the same
  row prefix as body rows and renders the message in the cell grid.
- Cell text is truncated to its assigned column width with no ellipsis by
  default, matching existing widget behavior.
- A column separator of two spaces is enough for the first slice. It should be
  a constant, not a constructor parameter, unless tests prove configurability is
  needed.

Column width allocation:

1. Start with the total visible width.
2. Reserve a row prefix budget of `min(2, target_width)` for every rendered
   table line, including the header and column-aligned empty state. Header and
   inactive body lines render spaces in this prefix slot so header and body
   cells stay aligned. At `target_width=1`, the active focused prefix truncates
   to `">"` and inactive/header prefixes truncate to one space.
3. The cell grid width is `max(0, target_width - prefix_budget)`. If it is
   zero, omit all cells and separators.
4. Reserve separator width between visible columns inside the remaining cell
   grid width.
5. Assign fixed `TableColumn.width` values first, clamped to at least
   `min_width`.
6. Distribute remaining width across flexible columns equally. Any remainder is
   assigned one cell at a time from left to right among flexible columns.
7. Flexible columns should receive at least `min_width` when possible.
8. If the total minimum width exceeds available width, shrink columns from
   right to left down to zero visible width as needed.
9. Omit cells whose assigned width is zero.

This avoids horizontal scrolling while keeping narrow terminals deterministic.

Alignment:

- `align="left"` pads on the right.
- `align="right"` pads on the left.
- Padding is based on `visible_width()`, not raw string length.

Focus indicators:

- Header rows should not change shape when the table gains focus.
- Body rows use a stable prefix:
  - `"> "` for the focused active row.
  - `"  "` for all other rows.
- Header rows reserve the same `"  "` prefix as body rows. The prefix is part
  of the visible width budget, so focused body rows, unfocused body rows, and
  header rows share the same cell grid width and must not exceed the same
  overall width.

## Input Behavior

`Table` implements local focus:

- `focus()` sets `focused=True`.
- `blur()` sets `focused=False`.

`handle_input(event)` behavior:

| Input | Behavior |
| --- | --- |
| `up` | Move to previous enabled row. |
| `down` | Move to next enabled row. |
| `home` | Move to first enabled row. |
| `end` | Move to last enabled row. |
| `enter` | Activate active enabled row. |
| `space` key | Activate active enabled row. |
| printable text `" "` | Activate active enabled row. |

`wrap` means navigation wrapping only. It never means cell text wrapping.

When `wrap=True`, `up` on the first enabled row moves to the last enabled row,
and `down` on the last enabled row moves to the first enabled row. When
`wrap=False`, those same inputs return `False` at the boundary and leave the
active row unchanged. `home` and `end` ignore `wrap`: they always target the
first or last enabled row.

Navigation returns:

- `True` when active row moved.
- `False` when input was understood but active row did not move because of a
  boundary.
- `None` when there are no enabled rows or the input is not consumed.

Activation returns:

- `callback_result(row.on_select())` when the row has a callback.
- `row.value` when there is no callback.
- `None` when there is no active enabled row.

Disabled rows:

- Render visibly disabled.
- Are skipped by navigation.
- Cannot be active after initialization unless all rows are disabled.
- Do not activate.

## Theme Tokens

Add these initial stable tokens:

| Token | Applies to |
| --- | --- |
| `widget.table.header` | Header cells. |
| `widget.table.row` | Enabled inactive body rows. |
| `widget.table.focus` | Focused active body row. |
| `widget.table.disabled` | Disabled body rows. |
| `widget.table.empty` | Empty-state text. |

The first slice should not style separators independently. A
`widget.table.separator` token can be added later if concrete styling needs
appear. Keeping separators unstyled avoids ANSI sequence fragmentation in early
width tests.

Theme application must use existing widget helpers such as `style_text()` and
must preserve visible width under `strip_control_sequences()`.

## Files In Scope

Production:

- `src/loushang/tui/ui_parts/widgets/table.py`
- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

Tests:

- `tests/tui/test_widgets_table.py`
- Existing import-boundary tests only if the new exports require updates there.

Docs and examples:

- `docs/en/reference/tui-widgets.md`
- `docs/zh-CN/reference/tui-widgets.md`
- `examples/tui/46_widgets_table.py`

## Testing Strategy

Use TDD for implementation:

1. Add export and constructor normalization tests.
2. Add rendering tests for headers, rows, fixed/flexible columns, left/right
   alignment, narrow widths, and short heights.
3. Add navigation tests for active row movement, wrapping, boundaries, disabled
   row skipping, and height-window visibility.
4. Add activation tests for callback rows, default row values, enter, space key,
   and printable space.
5. Add theme tests that assert ANSI output and visible width stability.
6. Add empty and no-column tests.
7. Add example importability test.
8. Implement the smallest code needed to pass each failing test group.

Expected verification commands:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_foundation.py tests/tui/test_widgets_hardening.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/46_widgets_table.py docs
```

## Rollout Plan

This should be one focused PR with small commits:

1. Commit the design spec.
2. Commit the implementation plan after spec review.
3. Add failing tests for table exports, rendering, input, and themes.
4. Implement `TableColumn`, `TableRow`, and `Table`.
5. Add exports.
6. Add docs and example.
7. Run focused tests, adjacent widget tests, full TUI tests, and Ruff.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Width allocation turns into a layout engine. | Keep only fixed plus equal flexible allocation; defer horizontal scrolling and resizing. |
| Table becomes a data-grid too early. | Exclude sorting, filtering, editing, and virtualization from this slice. |
| Mapping row default values are surprising. | Document that stable activation values require explicit `TableRow`. |
| ANSI styling breaks width calculations. | Assert stripped visible width in theme tests. |
| Disabled-row behavior drifts from `Menu`. | Reuse the same active-index and enabled-index semantics where possible. |

## Success Criteria

- `Table`, `TableColumn`, and `TableRow` are public exports from the same
  modules as existing stable widgets.
- Tables render deterministically within width and height constraints.
- Fixed and flexible column widths behave predictably on narrow and normal
  terminals.
- Active-row navigation works with enabled, disabled, wrapped, and non-wrapped
  rows.
- Row activation returns stable callback results or row values.
- Theme tokens apply without changing visible width.
- The example imports cleanly and demonstrates a realistic table composition.
- Existing TUI widget and render tests remain green.
