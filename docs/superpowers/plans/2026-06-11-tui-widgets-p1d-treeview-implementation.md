# TUI Widgets P1D TreeView Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `TreeNode` / `TreeView` widget for static hierarchical data with deterministic keyboard navigation, expansion state, selection intents, rendering, docs, and examples.

**Architecture:** Implement `TreeView` as one focused widget module under `src/loushang/tui/ui_parts/widgets/tree.py`. It normalizes a static `TreeNode` hierarchy into immutable internal entries, tracks expanded values and active value by node value, derives visible rows in preorder, and follows existing `Menu`/`Table` patterns for focus, activation, viewport, width constraints, theme tokens, tests, docs, and public exports.

**Tech Stack:** Python 3.11+, dataclasses with slots, existing `InputIntent`, `RenderResult`, `cell_width` helpers, `callback_result`, `is_activation_event`, `ThemeResolver`, pytest, Ruff.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-11-tui-widgets-p1d-treeview-design.md`
- Existing patterns:
  - `src/loushang/tui/ui_parts/widgets/menu.py`
  - `src/loushang/tui/ui_parts/widgets/table.py`
  - `src/loushang/tui/ui_parts/widgets/selection.py`
  - `src/loushang/tui/ui_parts/widgets/_utils.py`
  - `src/loushang/tui/input.py`
  - `tests/tui/test_widgets_light_controls.py`
  - `tests/tui/test_widgets_table.py`
  - `tests/tui/test_widgets_hardening.py`

## File Structure

Create:

- `src/loushang/tui/ui_parts/widgets/tree.py`
  - Owns public `TreeNode` and `TreeView`.
  - Owns internal normalized entries, flattening, expansion state, active-state fallback, input handling, activation, viewport, and row rendering.
- `tests/tui/test_widgets_tree.py`
  - Focused tests for exports, construction, duplicate handling, expansion normalization, navigation, expand/collapse, activation, rendering, theme tokens, and example importability.
- `examples/tui/49_widgets_tree.py`
  - Small runnable tree navigation example.

Modify:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
  - Re-export `TreeNode` and `TreeView`.
- `src/loushang/tui/ui_parts/__init__.py`
  - Re-export `TreeNode` and `TreeView`.
- `src/loushang/tui/__init__.py`
  - Re-export `TreeNode` and `TreeView`.
- `docs/en/reference/tui-widgets.md`
  - Add P1D TreeView entry, usage snippet, theme tokens, planned catalog update, and example link.
- `docs/zh-CN/reference/tui-widgets.md`
  - Mirror the English reference update.
- `tests/tui/test_widgets_hardening.py`
  - Add `TreeView` to small-constraint/theme coverage only if focused tests do not already cover those constraints clearly.

Do not modify:

- `InputIntentKind`, `InputRouter`, `SurfaceHost`, `Menu`, `Table`, `SelectList`, or global keybindings.

---

### Task 1: Add Failing Export And Construction Tests

**Files:**
- Create: `tests/tui/test_widgets_tree.py`

- [ ] **Step 1: Create the focused test file with shared helpers**

Use the helper style from `tests/tui/test_widgets_table.py`:

```python
from __future__ import annotations

import runpy
from typing import Any

import pytest

from loushang.tui import (
    InputEvent,
    RenderConstraints,
    ThemeResolver,
    TreeNode,
    TreeView,
    strip_control_sequences,
    visible_width,
)
from loushang.tui.ui_parts import TreeNode as UiTreeNode
from loushang.tui.ui_parts import TreeView as UiTreeView
from loushang.tui.ui_parts.widgets import TreeNode as WidgetTreeNode
from loushang.tui.ui_parts.widgets import TreeView as WidgetTreeView


def render_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def plain_lines(part: Any, *, width: int = 40, height: int = 8) -> tuple[str, ...]:
    return tuple(strip_control_sequences(line) for line in render_lines(part, width=width, height=height))


def assert_widths_within(lines: tuple[str, ...], width: int) -> None:
    assert all(visible_width(line) <= width for line in lines)


def intent_tuple(intent: object) -> tuple[str, str, str]:
    return (getattr(intent, "kind", ""), getattr(intent, "text", ""), getattr(intent, "note", ""))


def sample_nodes() -> tuple[TreeNode, ...]:
    return (
        TreeNode(
            "src",
            "src",
            expanded=True,
            children=(
                TreeNode("widgets", "widgets"),
                TreeNode("runtime", "runtime", disabled=True),
            ),
        ),
        TreeNode(
            "tests",
            "tests",
            children=(
                TreeNode("unit", "unit"),
                TreeNode("integration", "integration"),
            ),
        ),
    )
```

- [ ] **Step 2: Add failing public export tests**

```python
def test_tree_widgets_are_reexported_from_public_modules() -> None:
    assert TreeNode is UiTreeNode
    assert TreeNode is WidgetTreeNode
    assert TreeView is UiTreeView
    assert TreeView is WidgetTreeView
    assert TreeNode("src", "src").value == "src"
```

- [ ] **Step 3: Add failing construction and normalization tests**

```python
def test_tree_view_normalizes_expansion_and_active_state() -> None:
    tree = TreeView(sample_nodes(), expanded_values=("tests", "unit"), active_value="missing")

    assert tree.expanded_value_set == frozenset({"src", "tests"})
    assert tree.is_expanded("src") is True
    assert tree.is_expanded("widgets") is False
    assert tree.visible_values == ("src", "widgets", "runtime", "tests", "unit", "integration")
    assert tree.active_value == "src"


def test_tree_view_rejects_duplicate_values_and_unknown_expanded_values() -> None:
    with pytest.raises(ValueError):
        TreeView((TreeNode("dup", "One"), TreeNode("dup", "Two")))

    with pytest.raises(ValueError):
        TreeView(sample_nodes(), expanded_values=("missing",))


def test_tree_view_initial_active_falls_back_to_first_enabled_visible_node() -> None:
    tree = TreeView(
        (
            TreeNode("disabled", "Disabled", disabled=True),
            TreeNode("enabled", "Enabled"),
        ),
        active_value="disabled",
    )

    assert tree.active_value == "enabled"
```

- [ ] **Step 4: Run focused tests to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: FAIL during import because `TreeNode` and `TreeView` do not exist.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/tui/test_widgets_tree.py
git commit -m "test(tui): add treeview api tests"
```

---

### Task 2: Implement Tree Skeleton, Normalization, And Public Exports

**Files:**
- Create: `src/loushang/tui/ui_parts/widgets/tree.py`
- Modify: `src/loushang/tui/ui_parts/widgets/__init__.py`
- Modify: `src/loushang/tui/ui_parts/__init__.py`
- Modify: `src/loushang/tui/__init__.py`
- Test: `tests/tui/test_widgets_tree.py`

- [ ] **Step 1: Create `tree.py` with public classes and internal entry type**

```python
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import callback_result, is_activation_event, style_text

__all__ = ["TreeNode", "TreeView"]


@dataclass(frozen=True, slots=True)
class TreeNode:
    value: str
    label: str
    children: Sequence["TreeNode"] = ()
    disabled: bool = False
    expanded: bool = False
    on_select: Callable[[], object] | None = None


@dataclass(frozen=True, slots=True)
class _TreeEntry:
    value: str
    label: str
    depth: int
    parent: str
    children: tuple[str, ...]
    disabled: bool
    expanded: bool
    on_select: Callable[[], object] | None
```

- [ ] **Step 2: Add `TreeView` fields, properties, and normalization**

```python
@dataclass(init=False, slots=True)
class TreeView:
    nodes: Sequence[TreeNode]
    expanded_values: Sequence[str] = ()
    empty_text: str = "No nodes"
    wrap: bool = True
    indent: int = 2
    collapsed_marker: str = "+"
    expanded_marker: str = "-"
    leaf_marker: str = " "
    theme: ThemeResolver | None = None
    focused: bool = False
    _entries: dict[str, _TreeEntry] = field(default_factory=dict, init=False, repr=False)
    _root_values: tuple[str, ...] = field(default=(), init=False, repr=False)
    _expanded_values: set[str] = field(default_factory=set, init=False, repr=False)
    _active_value: str = field(default="", init=False, repr=False)
    _first_visible_index: int = field(default=0, init=False, repr=False)

    def __init__(
        self,
        nodes: Sequence[TreeNode],
        active_value: str = "",
        expanded_values: Sequence[str] = (),
        empty_text: str = "No nodes",
        wrap: bool = True,
        indent: int = 2,
        collapsed_marker: str = "+",
        expanded_marker: str = "-",
        leaf_marker: str = " ",
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None:
        self.nodes = tuple(nodes)
        self.expanded_values = tuple(expanded_values)
        self.empty_text = empty_text
        self.wrap = wrap
        self.indent = max(0, indent)
        self.collapsed_marker = collapsed_marker
        self.expanded_marker = expanded_marker
        self.leaf_marker = leaf_marker
        self.theme = theme
        self.focused = focused
        self._entries = {}
        self._root_values = tuple(node.value for node in self.nodes)
        for node in self.nodes:
            self._add_node(node, depth=0, parent="")
        self._expanded_values = self._initial_expanded_values()
        self._active_value = self._normalize_active_value(active_value)
        self._first_visible_index = 0

    @property
    def expanded_value_set(self) -> frozenset[str]:
        return frozenset(self._expanded_values)

    @property
    def visible_values(self) -> tuple[str, ...]:
        return tuple(entry.value for entry in self._visible_entries())

    @property
    def active_value(self) -> str:
        return self._active_value
```

`TreeView` uses `init=False` so `active_value` can be an initializer argument
while remaining a read-only property backed by `_active_value`.

- [ ] **Step 3: Implement normalization helpers**

```python
    def _add_node(self, node: TreeNode, *, depth: int, parent: str) -> None:
        if node.value in self._entries:
            raise ValueError(f"duplicate TreeNode value: {node.value!r}")
        children = tuple(child.value for child in node.children)
        self._entries[node.value] = _TreeEntry(
            value=node.value,
            label=node.label,
            depth=depth,
            parent=parent,
            children=children,
            disabled=node.disabled,
            expanded=node.expanded,
            on_select=node.on_select,
        )
        for child in node.children:
            self._add_node(child, depth=depth + 1, parent=node.value)

    def _initial_expanded_values(self) -> set[str]:
        expanded: set[str] = set()
        for entry in self._entries.values():
            if entry.expanded and entry.children:
                expanded.add(entry.value)
        for value in self.expanded_values:
            entry = self._entry(value)
            if entry.children:
                expanded.add(value)
        return expanded

    def _entry(self, value: str) -> _TreeEntry:
        try:
            return self._entries[value]
        except KeyError as exc:
            raise ValueError(f"unknown TreeNode value: {value!r}") from exc

    def _visible_entries(self) -> tuple[_TreeEntry, ...]:
        result: list[_TreeEntry] = []
        for value in self._root_values:
            self._append_visible(value, result)
        return tuple(result)

    def _append_visible(self, value: str, result: list[_TreeEntry]) -> None:
        entry = self._entries[value]
        result.append(entry)
        if entry.value not in self._expanded_values:
            return
        for child in entry.children:
            self._append_visible(child, result)

    def _enabled_visible_entries(self) -> tuple[_TreeEntry, ...]:
        return tuple(entry for entry in self._visible_entries() if not entry.disabled)

    def _normalize_active_value(self, preferred: str) -> str:
        visible = self._visible_entries()
        visible_enabled = {entry.value for entry in visible if not entry.disabled}
        if preferred in visible_enabled:
            return preferred
        return "" if not visible_enabled else next(entry.value for entry in visible if entry.value in visible_enabled)
```

- [ ] **Step 4: Implement minimal methods and render**

```python
    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def is_expanded(self, value: str) -> bool:
        entry = self._entry(value)
        return bool(entry.children and value in self._expanded_values)

    def expand(self, value: str) -> bool:
        entry = self._entry(value)
        if not entry.children or value in self._expanded_values:
            return False
        self._expanded_values.add(value)
        return True

    def collapse(self, value: str) -> bool:
        entry = self._entry(value)
        if not entry.children or value not in self._expanded_values:
            return False
        self._expanded_values.remove(value)
        self._repair_active_after_collapse(value)
        return True

    def toggle(self, value: str) -> bool:
        return self.collapse(value) if self.is_expanded(value) else self.expand(value)

    def handle_input(self, event: object) -> object:
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = autowrap_safe_width(constraints.width)
        height = max(0, constraints.max_height)
        if height == 0:
            return RenderResult.from_lines([], constraints=constraints)
        rows = self._visible_entries()
        if not rows:
            empty = truncate_to_width(self.empty_text, max_width=width, ellipsis="")
            return RenderResult.from_lines([RenderLine(style_text(empty, self.theme, "widget.tree.empty"))], constraints=constraints)
        lines = [RenderLine(truncate_to_width(entry.label, max_width=width, ellipsis="")) for entry in rows[:height]]
        return RenderResult.from_lines(lines, constraints=constraints)
```

Implement `_repair_active_after_collapse()` with the spec fallback in Task 4 if
not needed for Task 1 tests.

- [ ] **Step 5: Add public exports**

In `src/loushang/tui/ui_parts/widgets/__init__.py`:

```python
from .tree import TreeNode as TreeNode
from .tree import TreeView as TreeView
```

Add `"TreeNode"` and `"TreeView"` to `widgets.__all__`.

In `src/loushang/tui/ui_parts/__init__.py`:

```python
from .widgets import TreeNode as TreeNode
from .widgets import TreeView as TreeView
```

Add both names to `ui_parts.__all__`.

In `src/loushang/tui/__init__.py`, add both names to the existing
`from loushang.tui.ui_parts import (...)` block and to top-level `__all__`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: Task 1 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/tree.py src/loushang/tui/ui_parts/widgets/__init__.py src/loushang/tui/ui_parts/__init__.py src/loushang/tui/__init__.py
git commit -m "feat(tui): add treeview skeleton"
```

---

### Task 3: Add Failing Navigation, Expansion, And Activation Tests

**Files:**
- Modify: `tests/tui/test_widgets_tree.py`

- [ ] **Step 1: Add navigation tests**

```python
def test_tree_view_navigation_skips_disabled_and_honors_wrap_false() -> None:
    tree = TreeView(sample_nodes(), wrap=False)
    tree.focus()

    assert tree.active_value == "src"
    assert tree.handle_input(InputEvent(kind="key", key="down")) is True
    assert tree.active_value == "widgets"
    assert tree.handle_input(InputEvent(kind="key", key="down")) is True
    assert tree.active_value == "tests"
    assert tree.handle_input(InputEvent(kind="key", key="down")) is False
    assert tree.handle_input(InputEvent(kind="key", key="home")) is True
    assert tree.active_value == "src"
    assert tree.handle_input(InputEvent(kind="key", key="up")) is False


def test_tree_view_empty_and_all_disabled_navigation_returns_none() -> None:
    assert TreeView(()).handle_input(InputEvent(kind="key", key="down")) is None

    disabled = TreeView((TreeNode("disabled", "Disabled", disabled=True),))
    disabled.focus()
    assert disabled.active_value == ""
    assert disabled.handle_input(InputEvent(kind="key", key="down")) is None
    assert disabled.handle_input(InputEvent(kind="key", key="enter")) is None
```

- [ ] **Step 2: Add expand/collapse keyboard tests**

```python
def test_tree_view_right_expands_then_moves_to_enabled_direct_child() -> None:
    tree = TreeView((TreeNode("root", "root", children=(TreeNode("child", "child"),)),))
    tree.focus()

    assert tree.visible_values == ("root",)
    assert tree.handle_input(InputEvent(kind="key", key="right")) is True
    assert tree.expanded_value_set == frozenset({"root"})
    assert tree.visible_values == ("root", "child")
    assert tree.active_value == "root"
    assert tree.handle_input(InputEvent(kind="key", key="right")) is True
    assert tree.active_value == "child"


def test_tree_view_right_does_not_skip_disabled_direct_children_to_grandchildren() -> None:
    tree = TreeView(
        (
            TreeNode(
                "root",
                "root",
                expanded=True,
                children=(TreeNode("disabled", "disabled", disabled=True, children=(TreeNode("grand", "grand"),)),),
            ),
        )
    )
    tree.focus()

    assert tree.handle_input(InputEvent(kind="key", key="right")) is False
    assert tree.active_value == "root"


def test_tree_view_left_collapses_or_moves_to_enabled_parent() -> None:
    tree = TreeView(sample_nodes(), active_value="widgets")
    tree.focus()

    assert tree.handle_input(InputEvent(kind="key", key="left")) is True
    assert tree.active_value == "src"
    assert tree.handle_input(InputEvent(kind="key", key="left")) is True
    assert tree.expanded_value_set == frozenset()
    assert tree.active_value == "src"
    assert tree.handle_input(InputEvent(kind="key", key="left")) is False
```

- [ ] **Step 3: Add programmatic state and collapse fallback tests**

```python
def test_tree_view_programmatic_expand_collapse_toggle_and_unknown_values() -> None:
    tree = TreeView(sample_nodes())

    assert tree.expand("tests") is True
    assert tree.expand("tests") is False
    assert tree.is_expanded("tests") is True
    assert tree.collapse("tests") is True
    assert tree.collapse("tests") is False
    assert tree.toggle("tests") is True
    assert tree.toggle("tests") is True
    assert tree.expand("widgets") is False

    with pytest.raises(ValueError):
        tree.expand("missing")


def test_tree_view_collapse_hidden_active_falls_back_deterministically() -> None:
    tree = TreeView(sample_nodes(), expanded_values=("tests",), active_value="integration")
    tree.focus()

    assert tree.collapse("tests") is True

    assert tree.active_value == "tests"

    disabled_branch = TreeView(
        (
            TreeNode("before", "before"),
            TreeNode("branch", "branch", disabled=True, expanded=True, children=(TreeNode("child", "child"),)),
            TreeNode("after", "after"),
        ),
        active_value="child",
    )

    assert disabled_branch.collapse("branch") is True
    assert disabled_branch.active_value == "before"
```

- [ ] **Step 4: Add activation tests**

```python
def test_tree_view_activation_returns_callback_or_select_intent() -> None:
    calls: list[str] = []
    tree = TreeView(
        (
            TreeNode("callback", "callback", on_select=lambda: calls.append("callback")),
            TreeNode("plain", "plain"),
        )
    )
    tree.focus()

    assert tree.handle_input(InputEvent(kind="key", key="enter")) is True
    assert calls == ["callback"]
    assert tree.handle_input(InputEvent(kind="key", key="down")) is True
    assert intent_tuple(tree.handle_input(InputEvent(kind="key", key="enter"))) == ("select", "plain", "")
    assert intent_tuple(tree.handle_input(InputEvent(kind="key", key="space"))) == ("select", "plain", "")
    assert intent_tuple(tree.handle_input(InputEvent(kind="text", text=" "))) == ("select", "plain", "")
```

- [ ] **Step 5: Run focused tests to verify failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: FAIL on unimplemented navigation/input behavior.

- [ ] **Step 6: Commit failing tests**

```bash
git add tests/tui/test_widgets_tree.py
git commit -m "test(tui): cover treeview input behavior"
```

---

### Task 4: Implement Navigation, Expansion, Collapse Fallback, And Activation

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/tree.py`
- Test: `tests/tui/test_widgets_tree.py`

- [ ] **Step 1: Add active movement helpers**

```python
    def _move_active(self, delta: int) -> bool | None:
        enabled = tuple(entry.value for entry in self._enabled_visible_entries())
        if not enabled:
            return None
        if self._active_value not in enabled:
            self._active_value = enabled[0]
            return True
        position = enabled.index(self._active_value)
        next_position = position + delta
        if self.wrap:
            next_position %= len(enabled)
        elif next_position < 0 or next_position >= len(enabled):
            return False
        next_value = enabled[next_position]
        if next_value == self._active_value:
            return False
        self._active_value = next_value
        return True

    def _jump_active(self, *, first: bool) -> bool | None:
        enabled = tuple(entry.value for entry in self._enabled_visible_entries())
        if not enabled:
            return None
        target = enabled[0] if first else enabled[-1]
        if target == self._active_value:
            return False
        self._active_value = target
        return True
```

- [ ] **Step 2: Add parent/child and collapse fallback helpers**

```python
    def _active_entry(self) -> _TreeEntry | None:
        if not self._active_value:
            return None
        entry = self._entries.get(self._active_value)
        return None if entry is None or entry.disabled else entry

    def _first_enabled_direct_child(self, entry: _TreeEntry) -> str:
        for value in entry.children:
            child = self._entries[value]
            if not child.disabled:
                return value
        return ""

    def _nearest_enabled_visible_parent(self, entry: _TreeEntry) -> str:
        parent = entry.parent
        while parent:
            candidate = self._entries[parent]
            if not candidate.disabled and parent in self.visible_values:
                return parent
            parent = candidate.parent
        return ""

    def _repair_active_after_collapse(self, collapsed_value: str) -> None:
        visible_values = self.visible_values
        if self._active_value in visible_values:
            return
        collapsed = self._entries[collapsed_value]
        if not collapsed.disabled:
            self._active_value = collapsed_value
            return
        try:
            collapsed_index = visible_values.index(collapsed_value)
        except ValueError:
            collapsed_index = 0
        visible = self._visible_entries()
        for index in range(collapsed_index - 1, -1, -1):
            if not visible[index].disabled:
                self._active_value = visible[index].value
                return
        for index in range(collapsed_index + 1, len(visible)):
            if not visible[index].disabled:
                self._active_value = visible[index].value
                return
        self._active_value = ""
```

- [ ] **Step 3: Implement right/left and activation**

```python
    def _expand_or_move_child(self) -> bool | None:
        entry = self._active_entry()
        if entry is None:
            return None
        if not entry.children:
            return False
        if entry.value not in self._expanded_values:
            self._expanded_values.add(entry.value)
            return True
        child = self._first_enabled_direct_child(entry)
        if not child:
            return False
        if child == self._active_value:
            return False
        self._active_value = child
        return True

    def _collapse_or_move_parent(self) -> bool | None:
        entry = self._active_entry()
        if entry is None:
            return None
        if entry.children and entry.value in self._expanded_values:
            return self.collapse(entry.value)
        parent = self._nearest_enabled_visible_parent(entry)
        if not parent:
            return False
        self._active_value = parent
        return True

    def _activate(self) -> object:
        entry = self._active_entry()
        if entry is None:
            return None
        if entry.on_select is not None:
            return callback_result(entry.on_select())
        from loushang.tui.input import InputIntent

        return InputIntent(kind="select", text=entry.value)
```

Use a lazy import for `InputIntent` to avoid import cycles.

- [ ] **Step 4: Implement full `handle_input()`**

```python
    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = getattr(event, "key", "")
            if key == "up":
                return self._move_active(-1)
            if key == "down":
                return self._move_active(1)
            if key == "home":
                return self._jump_active(first=True)
            if key == "end":
                return self._jump_active(first=False)
            if key == "right":
                return self._expand_or_move_child()
            if key == "left":
                return self._collapse_or_move_parent()
        if is_activation_event(event):
            return self._activate()
        return None
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: all current tree tests PASS.

- [ ] **Step 6: Run adjacent tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py tests/tui/test_widgets_light_controls.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/tree.py
git commit -m "feat(tui): handle treeview input"
```

---

### Task 5: Add Failing Render, Viewport, Theme, Docs Example Tests

**Files:**
- Modify: `tests/tui/test_widgets_tree.py`

- [ ] **Step 1: Add render structure tests**

```python
def test_tree_view_renders_indentation_markers_focus_and_disabled_rows() -> None:
    tree = TreeView(sample_nodes())
    tree.focus()

    assert plain_lines(tree, width=30, height=6) == (
        "> - src",
        "      widgets",
        "      runtime",
        "  + tests",
    )
```

- [ ] **Step 2: Add width, empty, and viewport tests**

```python
def test_tree_view_respects_width_empty_and_height_viewport() -> None:
    empty = TreeView((), empty_text="Nothing here")
    assert plain_lines(empty, width=8, height=3) == ("Nothing",)

    tree = TreeView(
        tuple(TreeNode(str(index), f"Item {index}") for index in range(6)),
        active_value="5",
    )
    tree.focus()

    lines = render_lines(tree, width=8, height=3)

    assert plain_lines(tree, width=8, height=3) == (
        "    Item",
        "    Item",
        ">   Item",
    )
    assert_widths_within(lines, 8)
```

- [ ] **Step 3: Add theme token tests**

```python
def test_tree_view_applies_theme_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.tree.row": {"color": "white"},
            "widget.tree.focus": {"bold": True, "color": "green"},
            "widget.tree.disabled": {"dim": True},
            "widget.tree.empty": {"color": "bright_black"},
        }
    )
    tree = TreeView(sample_nodes(), theme=theme)
    tree.focus()

    raw = render_lines(tree, width=30, height=4)

    assert raw[0].startswith("\x1b[1;32m> - src")
    assert raw[1].startswith("\x1b[37m      widgets")
    assert raw[2].startswith("\x1b[2m      runtime")
    assert render_lines(TreeView((), theme=theme), width=10, height=1)[0].startswith("\x1b[90mNo nodes")
```

- [ ] **Step 4: Run focused tests to verify failures**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: FAIL on render/theme behavior.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/tui/test_widgets_tree.py
git commit -m "test(tui): cover treeview rendering"
```

---

### Task 6: Implement Deterministic Rendering And Viewport

**Files:**
- Modify: `src/loushang/tui/ui_parts/widgets/tree.py`
- Test: `tests/tui/test_widgets_tree.py`

- [ ] **Step 1: Implement marker, row, and viewport helpers**

```python
    def _ensure_active_visible(self, height: int) -> None:
        visible = self._visible_entries()
        if height <= 0 or not visible or not self._active_value:
            return
        index_by_value = {entry.value: index for index, entry in enumerate(visible)}
        active_index = index_by_value.get(self._active_value)
        if active_index is None:
            return
        if active_index < self._first_visible_index:
            self._first_visible_index = active_index
        elif active_index >= self._first_visible_index + height:
            self._first_visible_index = active_index - height + 1
        max_first = max(0, len(visible) - height)
        self._first_visible_index = max(0, min(self._first_visible_index, max_first))

    def _marker(self, entry: _TreeEntry) -> str:
        if not entry.children:
            return self.leaf_marker
        return self.expanded_marker if entry.value in self._expanded_values else self.collapsed_marker

    def _row_line(self, entry: _TreeEntry, width: int) -> str:
        focused_row = self.focused and entry.value == self._active_value and not entry.disabled
        prefix = "> " if focused_row else "  "
        indent = " " * (entry.depth * self.indent)
        text = truncate_to_width(f"{prefix}{indent}{self._marker(entry)} {entry.label}", max_width=width, ellipsis="")
        token = "widget.tree.disabled" if entry.disabled else "widget.tree.focus" if focused_row else "widget.tree.row"
        return style_text(text, self.theme, token)
```

- [ ] **Step 2: Replace `render()`**

```python
    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = autowrap_safe_width(constraints.width)
        height = max(0, constraints.max_height)
        if height == 0:
            return RenderResult.from_lines([], constraints=constraints)
        visible = self._visible_entries()
        if not visible:
            empty = truncate_to_width(self.empty_text, max_width=width, ellipsis="")
            return RenderResult.from_lines([RenderLine(style_text(empty, self.theme, "widget.tree.empty"))], constraints=constraints)
        self._ensure_active_visible(height)
        rows = visible[self._first_visible_index : self._first_visible_index + height]
        lines = [RenderLine(self._row_line(entry, width)) for entry in rows]
        return RenderResult.from_lines(lines, constraints=constraints)
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: PASS.

- [ ] **Step 4: Run adjacent hardening tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/tree.py
git commit -m "feat(tui): render treeview"
```

---

### Task 7: Add Docs And Runnable Example

**Files:**
- Create: `examples/tui/49_widgets_tree.py`
- Modify: `docs/en/reference/tui-widgets.md`
- Modify: `docs/zh-CN/reference/tui-widgets.md`
- Test: `tests/tui/test_widgets_tree.py`

- [ ] **Step 1: Add failing example import test**

```python
def test_widgets_tree_example_imports() -> None:
    namespace = runpy.run_path("examples/tui/49_widgets_tree.py", run_name="__test__")

    assert callable(namespace["build_app"])
```

- [ ] **Step 2: Run the example import test to verify failure**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py::test_widgets_tree_example_imports -q
```

Expected: FAIL because `examples/tui/49_widgets_tree.py` does not exist.

- [ ] **Step 3: Create `examples/tui/49_widgets_tree.py`**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    TreeNode,
    TreeView,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class TreeViewApp(FocusableMixin):
    tree: TreeView = field(
        default_factory=lambda: TreeView(
            (
                TreeNode("src", "src", expanded=True, children=(TreeNode("widgets", "widgets"), TreeNode("runtime", "runtime"))),
                TreeNode("tests", "tests", children=(TreeNode("unit", "unit"), TreeNode("integration", "integration"))),
            )
        )
    )
    message: str = "Use arrows to navigate. Enter selects. Press q to quit."

    def __post_init__(self) -> None:
        super().__init__()
        self.tree.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        tree_result = self.tree.render(RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2)))
        rows = [
            *tree_result.lines,
            RenderLine(""),
            RenderLine(truncate_to_width(self.message, max_width=constraints.width, ellipsis="")),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        result = self.tree.handle_input(event)
        if getattr(result, "kind", "") == "select":
            self.message = f"Selected: {getattr(result, 'text', '')}"
        return result


def build_app() -> Tui:
    tui = Tui()
    app = TreeViewApp()
    tui.add_child(app)
    tui.set_focus(app)
    return tui


async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if event.kind == "text" and "q" in event.text.lower():
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 4: Update English docs**

In `docs/en/reference/tui-widgets.md`:

- Add `P1D Tree Controls` after P1C.
- Add `TreeNode` / `TreeView` entry.
- Document right/left expand-collapse behavior and `select` intents.
- Add theme tokens `widget.tree.row`, `widget.tree.focus`, `widget.tree.disabled`, `widget.tree.empty`.
- Remove `TreeView` from planned catalog.
- Add example link.

Snippet:

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

- [ ] **Step 5: Update Chinese docs**

Mirror the English content in `docs/zh-CN/reference/tui-widgets.md`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add examples/tui/49_widgets_tree.py docs/en/reference/tui-widgets.md docs/zh-CN/reference/tui-widgets.md tests/tui/test_widgets_tree.py
git commit -m "docs(tui): document treeview widget"
```

---

### Task 8: Final Verification And Cleanup

**Files:**
- Review all changed files.

- [ ] **Step 1: Run focused TreeView tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_tree.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent widget tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_table.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_hardening.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full TUI tests**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
```

Expected: PASS.

- [ ] **Step 4: Run Ruff on touched surfaces**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev ruff check src/loushang/tui tests/tui examples/tui/49_widgets_tree.py docs
```

Expected: PASS.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git diff --stat origin/main...HEAD
git diff --check
```

Expected: no whitespace errors; diff contains only spec/plan, TreeView widget,
exports, tests, docs, and example.

- [ ] **Step 6: Commit any final fixes**

If verification required small fixes:

```bash
git add <fixed-files>
git commit -m "fix(tui): finalize treeview widget"
```

If no fixes were needed, do not create an empty commit.

---

## Success Criteria

- `TreeNode` and `TreeView` are exported from `loushang.tui`, `loushang.tui.ui_parts`, and `loushang.tui.ui_parts.widgets`.
- Duplicate values and unknown `expanded_values` raise `ValueError`.
- Initial expansion ignores leaf values and preserves only expanded branches.
- Navigation skips disabled visible nodes and keeps active row in the viewport.
- `right` expands collapsed branches or moves to first enabled direct child only.
- `left` collapses expanded branches or moves to nearest enabled visible parent.
- Programmatic expand/collapse/toggle/is-expanded semantics match the spec.
- Activation returns callbacks or `InputIntent(kind="select", text=value)`.
- Rendering obeys width and height constraints with deterministic ASCII markers.
- Theme tokens are deterministic and covered.
- Docs and example import tests pass.
- Existing TUI tests remain green.
