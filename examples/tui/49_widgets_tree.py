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

LABEL_WIDTH = 14

NODE_DETAILS = {
    "src": ("src", "folder", "expanded"),
    "widgets": ("src/widgets", "folder", "leaf"),
    "runtime": ("src/runtime", "folder", "leaf"),
    "tests": ("tests", "folder", "collapsed"),
    "unit": ("tests/unit", "folder", "leaf"),
    "integration": ("tests/integration", "folder", "leaf"),
}


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


@dataclass(slots=True)
class TreeViewApp(FocusableMixin):
    tree: TreeView = field(default_factory=lambda: TreeView(_nodes()))
    selected_value: str = ""

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.tree.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        tree_result = self.tree.render(
            RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 9))
        )
        active_value = self.tree.active_value
        path, kind, status = NODE_DETAILS.get(active_value, ("", "", ""))
        if self.selected_value == active_value:
            status = f"Selected: {path}"
        rows = [
            RenderLine(truncate_to_width("Project Explorer", max_width=constraints.width, ellipsis="")),
            RenderLine(""),
            RenderLine("Tree"),
            *tree_result.lines,
            RenderLine(""),
            RenderLine("Details"),
            _field("Path", path, width=constraints.width),
            _field("Kind", kind, width=constraints.width),
            _field("Status", status, width=constraints.width),
            RenderLine(""),
            RenderLine(
                truncate_to_width(
                    "[up/down] node  [enter] select/toggle  [q] quit",
                    max_width=constraints.width,
                    ellipsis="",
                )
            ),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        result = self.tree.handle_input(event)
        if getattr(result, "kind", "") == "select":
            self.selected_value = getattr(result, "text", "")
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


def _nodes() -> tuple[TreeNode, ...]:
    return (
        TreeNode(
            "src",
            "src",
            expanded=True,
            children=(
                TreeNode("widgets", "widgets"),
                TreeNode("runtime", "runtime"),
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


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
