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

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = autowrap_safe_width(constraints.width)
        height = max(0, constraints.max_height)
        if height == 0:
            return RenderResult.from_lines([], constraints=constraints)
        rows = self._visible_entries()
        if not rows:
            empty = truncate_to_width(self.empty_text, max_width=width, ellipsis="")
            return RenderResult.from_lines(
                [RenderLine(style_text(empty, self.theme, "widget.tree.empty"))],
                constraints=constraints,
            )
        lines = [RenderLine(truncate_to_width(entry.label, max_width=width, ellipsis="")) for entry in rows[:height]]
        return RenderResult.from_lines(lines, constraints=constraints)
