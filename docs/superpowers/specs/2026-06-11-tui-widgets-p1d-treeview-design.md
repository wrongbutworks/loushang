# TUI Widgets P1D TreeView Design

## Status

Draft for spec review.

## Context

`loushang.tui` now has a useful first widget catalog:

- P0A foundation widgets: buttons, choices, fields, forms, dialogs.
- P0B small controls: badges, status pills, progress, key-value lists, toolbar.
- P0C light controls: menu, tabs, spinner.
- P1A data controls: table.
- P1B/P1C text and dialog inputs: textarea and question dialog.

The next gap is a reusable tree widget for hierarchical data. Callers can fake
this with `Menu` or `Table`, but they must hand-roll flattening, indentation,
expand/collapse state, active row visibility, disabled nodes, and selection
intent wiring. `TreeView` should provide that foundation without taking on file
system, async loading, or checkbox-tree behavior.

## Goals

- Add a public `TreeNode` data class and `TreeView` widget.
- Support static nested trees with unique node values.
- Support local focus, active-row navigation, expand/collapse, and activation.
- Return structured `InputIntent(kind="select", text=node.value)` by default.
- Allow per-node `on_select` callbacks to override the default return value.
- Skip disabled nodes for active navigation and activation while still rendering
  them.
- Keep active rows visible inside a height-constrained viewport.
- Render deterministic ASCII tree rows under narrow width and short height.
- Export stable public API through `loushang.tui.ui_parts.widgets`,
  `loushang.tui.ui_parts`, and top-level `loushang.tui`.
- Add focused tests, docs, and a small example.

## Non-Goals

- Do not add lazy loading or async child providers in P1D.
- Do not read the file system or provide a file browser widget.
- Do not add multi-select, checkbox tree, drag/drop, search, filter, or typeahead.
- Do not add mouse support.
- Do not add inline rename/edit behavior.
- Do not change `InputRouter`, `SurfaceHost`, `Menu`, `Table`, or
  `SelectList`.
- Do not introduce new `InputIntentKind` values; reuse existing `select`.

## Public API

Add `src/loushang/tui/ui_parts/widgets/tree.py`.

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class TreeNode:
    value: str
    label: str
    children: Sequence["TreeNode"] = ()
    disabled: bool = False
    expanded: bool = False
    on_select: Callable[[], object] | None = None


@dataclass(slots=True)
class TreeView:
    nodes: Sequence[TreeNode]
    active_value: str = ""
    expanded_values: Sequence[str] = ()
    empty_text: str = "No nodes"
    wrap: bool = True
    indent: int = 2
    collapsed_marker: str = "+"
    expanded_marker: str = "-"
    leaf_marker: str = " "
    theme: ThemeResolver | None = None
    focused: bool = False
```

The first public API should also expose:

- `focus()` and `blur()`.
- `handle_input(event)`.
- `render(constraints)`.
- `expanded_value_set` as a read-only property returning `frozenset[str]`.
- `visible_values` as a read-only property returning the currently visible node
  values in render/navigation order.
- `expand(value)`, `collapse(value)`, and `toggle(value)`.
- `is_expanded(value)`.

`TreeView` normalizes `nodes` to immutable internal entries in `__post_init__`.
Node `value` values must be unique across the tree. Duplicate values raise
`ValueError` during construction because expansion, active row, and selection
state are value-keyed.

Initial expansion state is the union of:

- each `TreeNode(expanded=True)`;
- `TreeView(expanded_values=...)`.

Initial active state:

- if `active_value` names an enabled visible node, use it;
- otherwise choose the first enabled visible node;
- if no enabled visible node exists, use `""`.

## Input Behavior

Default keys:

| Input | Behavior |
| --- | --- |
| `up` | Move to previous enabled visible node. |
| `down` | Move to next enabled visible node. |
| `home` | Move to first enabled visible node. |
| `end` | Move to last enabled visible node. |
| `right` | Expand collapsed active branch, or move to first enabled child when already expanded. |
| `left` | Collapse expanded active branch, or move to nearest enabled visible parent. |
| `enter` / `space` | Activate active node. |
| text event containing literal space | Activate active node. |

Movement returns:

- `True` when active or expansion state changes;
- `False` at a non-wrapping boundary with no state change;
- `None` when there is no enabled visible node.

Activation returns:

- `None` when there is no active enabled node;
- `callback_result(node.on_select())` when `on_select` is provided;
- otherwise `InputIntent(kind="select", text=node.value)`.

`right` semantics:

1. If active node has children and is collapsed, expand it and return `True`.
2. If active node is expanded, move to the first enabled visible descendant that
   is now immediately under that branch and return `True`.
3. If neither applies, return `False`.

`left` semantics:

1. If active node has children and is expanded, collapse it and return `True`.
2. Otherwise move to the nearest enabled visible parent and return `True`.
3. If there is no enabled visible parent, return `False`.

Disabled nodes:

- are visible;
- may be expanded initially or through `expand(value)` if a caller controls
  state programmatically;
- are skipped by keyboard active navigation;
- are not activated.

## Rendering

`TreeView.render(constraints)` returns visible rows in preorder. Children render
only when all ancestors are expanded.

Default row shape:

```text
{focus_prefix}{indent}{marker} {label}
```

Where:

- `focus_prefix` is `"> "` for the active focused row, otherwise `"  "`;
- `indent` is `" " * (depth * indent)`;
- `marker` is `collapsed_marker` for collapsed branches, `expanded_marker` for
  expanded branches, and `leaf_marker` for leaves.

Examples:

```text
> - src
      widgets
  + tests
```

Rows are truncated with `truncate_to_width(..., ellipsis="")` against
`autowrap_safe_width(constraints.width)`.

When `nodes` is empty, render one `empty_text` row with `widget.tree.empty`.

Viewport behavior:

- `TreeView` keeps `_first_visible_index` so the active row stays in view.
- The visible window is based on flattened visible rows, not total node count.
- Collapsing a branch that hides the active node moves active state to the
  collapsed branch if that branch is enabled; otherwise to the nearest enabled
  visible node.
- `constraints.max_height <= 0` renders no lines.

## Theme Tokens

Add these initial stable tokens:

| Token | Applies to |
| --- | --- |
| `widget.tree.row` | Enabled inactive rows. |
| `widget.tree.focus` | Focused active row. |
| `widget.tree.disabled` | Disabled rows. |
| `widget.tree.empty` | Empty-state row. |

P1D does not style disclosure markers separately; each row is styled as one
line. A future slice can add marker-specific tokens if needed.

## Files In Scope

Production:

- `src/loushang/tui/ui_parts/widgets/tree.py`
- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

Tests:

- `tests/tui/test_widgets_tree.py`
- Adjacent widget hardening tests only if constraint/theme coverage is clearer
  there.

Docs and examples:

- `docs/en/reference/tui-widgets.md`
- `docs/zh-CN/reference/tui-widgets.md`
- `examples/tui/49_widgets_tree.py`

## Testing Strategy

Use TDD for implementation:

1. Add public export tests.
2. Add construction tests for normalization, duplicate value rejection, initial
   expanded values, and initial active fallback.
3. Add navigation tests for up/down/home/end, wrap false boundaries, disabled
   node skipping, and empty/all-disabled trees.
4. Add expand/collapse tests for right/left, programmatic methods, and active
   fallback when collapsing hides active descendants.
5. Add activation tests for enter, key-space, text-space, callbacks, and default
   `InputIntent(kind="select", text=value)`.
6. Add render tests for indentation, markers, focus prefix, disabled rows,
   empty state, width truncation, height viewport, and theme tokens.
7. Add docs and example importability tests.
8. Run focused tests, adjacent widget tests, full TUI tests, and Ruff.

Expected verification commands:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_hardening.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/49_widgets_tree.py docs
```

## Rollout Plan

This should be one focused PR with small commits:

1. Commit the design spec.
2. Commit the implementation plan after spec review.
3. Add failing export and construction tests.
4. Implement `TreeNode`, `TreeView` skeleton, normalization, and public exports.
5. Add failing navigation, expand/collapse, and activation tests.
6. Implement input behavior and programmatic state methods.
7. Add failing render/theme/constraint tests.
8. Implement deterministic rendering and viewport handling.
9. Add docs and example coverage.
10. Run focused, adjacent, full TUI, and Ruff verification.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Tree values are duplicated and expansion state becomes ambiguous. | Reject duplicate values during construction. |
| Lazy loading pressure bloats P1D. | Keep P1D static; add async/lazy behavior only after real callers appear. |
| Keyboard semantics diverge from common tree behavior. | Use standard right-expand/left-collapse behavior and cover it with tests. |
| Collapsing branches hides active state unexpectedly. | Define fallback rules and test them. |
| Tree rendering breaks narrow terminals. | Use existing width helpers and constraint tests. |
| `TreeView` overlaps too much with `Menu`. | Keep `TreeView` focused on hierarchy, expansion state, and indentation. |

## Success Criteria

- `TreeNode` and `TreeView` are exported from public TUI modules.
- Duplicate node values raise `ValueError`.
- Visible flattening respects expansion state.
- Navigation skips disabled nodes and keeps active row visible.
- Right/left expand, collapse, and parent/child movement are deterministic.
- Activation returns callbacks or `InputIntent(kind="select", text=value)`.
- Rendering obeys width and height constraints with deterministic ASCII markers.
- Theme tokens are deterministic and covered.
- Docs and example import tests pass.
- Existing TUI tests remain green.
