# TreeView

`TreeView` is a reusable focused widget for hierarchical lists. It is intended
for project explorers, settings category trees, diagnostics groups, and other
bounded tree-shaped navigation inside page content.

It owns flattening expanded nodes into visible rows, active-node repair,
disabled-node skipping, expand/collapse behavior, viewport windowing, row
markers, and structured activation results. Product pages still own selected
detail panels, persistence, cross-page status messages, and global footer text.

## Inputs And State

- `TreeNode(value, label, children=(), disabled=False, expanded=False,
  on_select=None)`.
- `active_value`: initial active enabled visible node.
- `expanded_values`: additional expanded node values.
- `empty_text`: text shown when there are no nodes.
- `wrap`: whether up/down navigation wraps between first and last enabled
  visible nodes.
- `indent`, `collapsed_marker`, `expanded_marker`, and `leaf_marker`: row
  presentation controls.
- `theme`: optional `ThemeResolver`.

`value` must be unique across the full tree. `expanded_values` may only contain
known nodes with children. Unknown or duplicate values fail early during
construction.

## Layout Behavior

Rendering order is the visible tree slice only. TreeView does not render local
headers, details, overflow rows, or footers.

Each rendered row contains:

1. a focus prefix (`> ` for the active focused row, otherwise two spaces)
2. depth indentation
3. a collapsed, expanded, or leaf marker
4. the node label

Rows are truncated to the available width. The viewport scrolls just enough to
keep the active visible node in the rendered height. When focused, TreeView
declares a cursor at column 0 on the active visible row so parent layouts can
offset it through page chrome.

## Focus And Activation

TreeView handles these keys when focused:

- `up` / `down`: move between enabled visible nodes.
- `home` / `end`: jump to the first or last enabled visible node.
- `right`: expand an expandable active node, or move to its first enabled
  direct child when already expanded.
- `left`: collapse an expanded active node, or move to the nearest enabled
  visible parent.
- `enter` / `space`: run `on_select` or return `InputIntent(kind="select",
  text=value)`.

Disabled nodes remain visible but are skipped by navigation and cannot be
activated. Descendants of a disabled node are not automatically promoted as
direct-child navigation targets.

TreeView does not define a page-level focus escape. A wrapper page may translate
an edge result, for example `up` on the first visible row, into `None` so
`PageScaffold` or `TabGroup` can move focus to a header.

## Theme Tokens

| Token | Applies to |
| --- | --- |
| `widget.tree.row` | Normal enabled rows |
| `widget.tree.focus` | Active row while TreeView has focus |
| `widget.tree.disabled` | Disabled rows |
| `widget.tree.empty` | Empty tree row |

## Composition

TreeView can live directly inside page content, inside a small page object that
adds details next to or below the tree, or inside `PageScaffold` body content.
Parent pages should preserve TreeView's cursor declaration when adding local
chrome, then let `PageScaffold` offset the body cursor through header,
separator, padding, and footer rows.

Use page-level footer/status components for global commands and state. Keep
TreeView rows limited to tree navigation and labels.

## Test Obligations

Changes to TreeView should cover:

- duplicate and unknown value validation
- initial expansion and active-node repair
- disabled-node visibility and navigation skipping
- up/down/home/end movement with and without wrapping
- left/right expand, collapse, and parent/child movement
- activation callback and `InputIntent` results
- bounded viewport and cursor declaration on the active visible row
- row width truncation and empty-state rendering
- theme tokens preserving visible text
- composition playback with `PageScaffold` when cursor offsets matter
