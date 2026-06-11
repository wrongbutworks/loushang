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
    tree: TreeView = field(default_factory=lambda: TreeView(_nodes()))
    message: str = "Use arrows to navigate. Enter selects. Press q to quit."

    def __post_init__(self) -> None:
        super().__init__()
        self.tree.focus()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        tree_result = self.tree.render(
            RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2))
        )
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
