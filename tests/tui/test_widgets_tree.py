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
                children=(
                    TreeNode(
                        "disabled",
                        "disabled",
                        disabled=True,
                        children=(TreeNode("grand", "grand"),),
                    ),
                ),
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
            TreeNode(
                "branch",
                "branch",
                disabled=True,
                expanded=True,
                children=(TreeNode("child", "child"),),
            ),
            TreeNode("after", "after"),
        ),
        active_value="child",
    )

    assert disabled_branch.collapse("branch") is True
    assert disabled_branch.active_value == "before"


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


def test_tree_view_renders_indentation_markers_focus_and_disabled_rows() -> None:
    tree = TreeView(sample_nodes())
    tree.focus()

    assert plain_lines(tree, width=30, height=6) == (
        "> - src",
        "      widgets",
        "      runtime",
        "  + tests",
    )


def test_tree_view_respects_width_empty_and_height_viewport() -> None:
    empty = TreeView((), empty_text="Nothing here")
    assert plain_lines(empty, width=8, height=3) == ("Nothing",)

    tree = TreeView(
        tuple(TreeNode(str(index), f"Item {index}") for index in range(6)),
        active_value="5",
    )
    tree.focus()

    lines = render_lines(tree, width=9, height=3)

    assert plain_lines(tree, width=9, height=3) == (
        "    Item",
        "    Item",
        ">   Item",
    )
    assert_widths_within(lines, 9)


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
