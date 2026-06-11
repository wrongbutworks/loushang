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


def test_tree_widgets_are_reexported_from_public_modules() -> None:
    assert TreeNode is UiTreeNode
    assert TreeNode is WidgetTreeNode
    assert TreeView is UiTreeView
    assert TreeView is WidgetTreeView
    assert TreeNode("src", "src").value == "src"


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
