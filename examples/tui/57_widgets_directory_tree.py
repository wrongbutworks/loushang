from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loushang.tui import (
    DirectoryTree,
    DirectoryTreeSelect,
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    apply_theme_style,
    truncate_to_width,
)

DIRECTORY_TREE_THEME = ThemeResolver(
    defaults={
        "example.directoryTree.title": {"color": "cyan", "bold": True},
        "example.directoryTree.meta": {"color": "bright_black"},
        "example.directoryTree.status": {"color": "green"},
        "example.directoryTree.footer": {"color": "bright_black"},
        "widget.tree.row": {"color": "white"},
        "widget.tree.focus": {"color": "cyan", "bold": True},
        "widget.tree.disabled": {"dim": True},
        "widget.tree.empty": {"color": "bright_black"},
        "widget.directoryTree.directory": {"color": "cyan"},
        "widget.directoryTree.file": {"color": "white"},
        "widget.directoryTree.empty": {"color": "bright_black", "dim": True},
        "widget.directoryTree.sentinel": {"color": "yellow", "dim": True},
        "widget.directoryTree.error": {"color": "red", "dim": True},
    }
)


def _style(text: str, token: str) -> str:
    return apply_theme_style(text, DIRECTORY_TREE_THEME.resolve(token))


def _styled_line(text: str, token: str, *, width: int) -> RenderLine:
    return RenderLine(_style(truncate_to_width(text, max_width=width, ellipsis=""), token))


@dataclass(slots=True)
class DirectoryTreeExampleApp(FocusableMixin):
    _tmpdir: tempfile.TemporaryDirectory[str] = field(default_factory=tempfile.TemporaryDirectory)
    show_hidden: bool = False
    status: str = "Ready"
    root: Path = field(init=False)
    tree: DirectoryTree = field(init=False)

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.root = Path(self._tmpdir.name)
        _build_fixture(self.root)
        self.tree = self._new_tree()
        self.tree.focus()

    def _new_tree(self) -> DirectoryTree:
        active_path = self.tree.active_path if hasattr(self, "tree") else None
        return DirectoryTree(
            root=self.root,
            active_path=active_path,
            expanded_paths=(self.root, self.root / "src", self.root / "empty"),
            show_hidden=self.show_hidden,
            theme=DIRECTORY_TREE_THEME,
        )

    def render(self, constraints: RenderConstraints) -> RenderResult:
        tree_height = max(1, constraints.max_height - 8)
        tree_result = self.tree.render(RenderConstraints(width=constraints.width, max_height=tree_height))
        rows = [
            _styled_line("Directory Tree", "example.directoryTree.title", width=constraints.width),
            _styled_line(f"Root {self.root}", "example.directoryTree.meta", width=constraints.width),
            _styled_line(
                f"Hidden {'on' if self.show_hidden else 'off'}",
                "example.directoryTree.meta",
                width=constraints.width,
            ),
            RenderLine(""),
            *tree_result.lines,
            RenderLine(""),
            _styled_line(self.status, "example.directoryTree.status", width=constraints.width),
            _styled_line(
                "[up/down] move  [enter/space] select  [h] hidden  [r] reload  [q] quit",
                "example.directoryTree.footer",
                width=constraints.width,
            ),
        ]
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints)

    def handle_input(self, event: Any) -> object:
        if getattr(event, "kind", "") == "text":
            text = getattr(event, "text", "").lower()
            if "h" in text:
                self.show_hidden = not self.show_hidden
                self.tree = self._new_tree()
                self.tree.focus()
                self.status = "Hidden files shown" if self.show_hidden else "Hidden files hidden"
                return True
            if "r" in text:
                self.tree.reload()
                self.status = "Reloaded"
                return True
        result = self.tree.handle_input(event)
        if isinstance(result, DirectoryTreeSelect):
            self.status = f"Selected: {result.path.name or result.path}"
        return result


def build_app() -> Tui:
    tui = Tui()
    app = DirectoryTreeExampleApp()
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


def _build_fixture(root: Path) -> None:
    (root / "src" / "widgets").mkdir(parents=True)
    (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "README.md").write_text("# DirectoryTree example\n", encoding="utf-8")
    (root / ".env").write_text("EXAMPLE=1\n", encoding="utf-8")
    (root / "empty").mkdir()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
