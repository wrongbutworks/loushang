from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    FocusableMixin,
    InputEvent,
    PageScaffold,
    PageScaffoldContext,
    RenderConstraints,
    RenderLine,
    RenderResult,
    TabItem,
    Tabs,
    ThemeResolver,
    TreeNode,
    TreeView,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

LABEL_WIDTH = 14

TREE_PAGE_THEME = ThemeResolver(
    defaults={
        "widget.tabs.tab": {"color": "white"},
        "widget.tabs.selected": {"bold": True, "color": "green"},
        "widget.tabs.focus": {"bold": True, "color": "cyan"},
        "widget.tabs.level0.selected_header_focus": {"bold": True, "color": "cyan"},
        "widget.tabs.level0.selected_content_focus": {"bold": True, "color": "green"},
        "widget.pageScaffold.separator": {"color": "bright_black"},
        "widget.pageScaffold.footer": {"color": "bright_black"},
        "widget.tree.row": {"color": "white"},
        "widget.tree.focus": {"bold": True, "color": "cyan"},
        "widget.tree.disabled": {"dim": True},
        "widget.tree.empty": {"color": "bright_black"},
    }
)


@dataclass(slots=True)
class TreePage(FocusableMixin):
    title: str
    tree: TreeView
    details: dict[str, tuple[str, str, str]]
    selected_value: str = ""

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)

    def focus(self) -> None:
        self.focused = True
        self.tree.focus()

    def blur(self) -> None:
        self.focused = False
        self.tree.blur()

    def handle_input(self, event: Any) -> object:
        key = getattr(event, "key", "") if getattr(event, "kind", "") == "key" else ""
        if key == "up" and self.tree.active_value == self._first_visible_value():
            return None
        result = self.tree.handle_input(event)
        if getattr(result, "kind", "") == "select":
            self.selected_value = getattr(result, "text", "")
            path, _, _ = self.details.get(self.selected_value, ("", "", ""))
            return f"Selected: {path}"
        return result

    def render(self, constraints: RenderConstraints) -> RenderResult:
        tree_height = max(1, constraints.max_height - 6)
        tree_result = self.tree.render(RenderConstraints(width=constraints.width, max_height=tree_height))
        active_value = self.tree.active_value
        path, kind, status = self.details.get(active_value, ("", "", ""))
        if self.selected_value == active_value and path:
            status = f"Selected: {path}"

        rows = [
            RenderLine(truncate_to_width(self.title, max_width=constraints.width, ellipsis="")),
            *tree_result.lines,
            RenderLine(""),
            RenderLine("Details"),
            _field("Path", path, width=constraints.width),
            _field("Kind", kind, width=constraints.width),
            _field("Status", status, width=constraints.width),
        ]
        cursor = None
        if tree_result.cursor is not None:
            cursor = CursorDeclaration(row=1 + tree_result.cursor.row, column=tree_result.cursor.column)
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

    def _first_visible_value(self) -> str:
        return self.tree.visible_values[0] if self.tree.visible_values else ""


@dataclass(slots=True)
class TreeScaffoldDemo(FocusableMixin):
    tabs: Tabs = field(init=False)
    pages: dict[str, TreePage] = field(init=False)
    scaffold: PageScaffold = field(init=False)
    status: str = "Ready"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.tabs = Tabs(
            (
                TabItem("files", "Files"),
                TabItem("settings", "Settings"),
            ),
            on_change=self._select_tab,
            theme=TREE_PAGE_THEME,
        )
        self.pages = {
            "files": TreePage("Project tree", _files_tree(), _file_details()),
            "settings": TreePage("Project tree", _settings_tree(), _settings_details()),
        }
        self.scaffold = PageScaffold(
            header=self.tabs,
            body=self.pages[self.tabs.value],
            footer=self._footer,
            theme=TREE_PAGE_THEME,
            focused=True,
            focus_region="body",
            separator_after_header=True,
            body_padding_top=1,
            body_padding_bottom=1,
        )
        self.focus()

    def focus(self) -> None:
        self.focused = True
        self.scaffold.focus()

    def blur(self) -> None:
        self.focused = False
        self.scaffold.blur()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        self.tabs.selected_focus = "header" if self.scaffold.focus_region == "header" else "content"
        return self.scaffold.render(constraints)

    def handle_input(self, event: Any) -> object:
        result = self.scaffold.handle_input(event)
        if isinstance(result, str):
            self.status = result
            return True
        return True if result is not None else None

    def _select_tab(self, value: str) -> bool:
        self.scaffold.body = self.pages[value]
        self.scaffold.focus_region = "header"
        self.status = f"Selected: {value.title()}"
        return True

    def _footer(self, context: PageScaffoldContext) -> str:
        if context.focus_region == "header":
            return f"Tabs | {self.status} | Left/Right switch | Down tree | q quit"
        return f"Tree | {self.status} | Up/Down move | Left/Right collapse/expand | Enter select | q quit"


def build_app() -> Tui:
    tui = Tui()
    app = TreeScaffoldDemo()
    tui.add_child(app)
    tui.set_focus(app)
    return tui


async def main() -> int:
    tui = build_app()

    async def on_input(event: InputEvent, context: Any) -> TuiInputResult:
        if _should_quit(event):
            return context.stop(0)
        context.tui.handle_input(event)
        return TuiInputResult()

    return await TuiRunner(tui).run(on_input=on_input)


def _field(label: str, value: str, *, width: int) -> RenderLine:
    text = f"{label:<{LABEL_WIDTH}}{value}"
    return RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))


def _files_tree() -> TreeView:
    return TreeView(
        (
            TreeNode(
                "src",
                "src",
                expanded=True,
                children=(
                    TreeNode("tui", "tui", children=(TreeNode("widgets", "widgets"), TreeNode("runtime", "runtime"))),
                    TreeNode("coding", "coding"),
                ),
            ),
            TreeNode("tests", "tests", children=(TreeNode("unit", "unit"), TreeNode("playback", "playback"))),
            TreeNode("docs", "docs", children=(TreeNode("internals", "internals"),)),
        ),
        theme=TREE_PAGE_THEME,
        wrap=False,
    )


def _settings_tree() -> TreeView:
    return TreeView(
        (
            TreeNode(
                "config",
                "Config",
                children=(
                    TreeNode("model", "Model"),
                    TreeNode("status-line", "Status line"),
                    TreeNode("permissions", "Permissions"),
                ),
            ),
            TreeNode(
                "status",
                "Status",
                children=(TreeNode("session", "Session"), TreeNode("runtime", "Runtime")),
            ),
            TreeNode("stats", "Stats", children=(TreeNode("overview", "Overview"), TreeNode("models", "Models"))),
        ),
        theme=TREE_PAGE_THEME,
        wrap=False,
    )


def _file_details() -> dict[str, tuple[str, str, str]]:
    return {
        "src": ("src", "folder", "expanded"),
        "tui": ("src/tui", "folder", "collapsed"),
        "widgets": ("src/tui/widgets", "folder", "leaf"),
        "runtime": ("src/tui/runtime", "folder", "leaf"),
        "coding": ("src/coding", "folder", "leaf"),
        "tests": ("tests", "folder", "collapsed"),
        "unit": ("tests/unit", "folder", "leaf"),
        "playback": ("tests/playback", "folder", "leaf"),
        "docs": ("docs", "folder", "collapsed"),
        "internals": ("docs/internals", "folder", "leaf"),
    }


def _settings_details() -> dict[str, tuple[str, str, str]]:
    return {
        "config": ("Config", "tab", "collapsed"),
        "model": ("Config / Model", "setting", "opens model tab"),
        "status-line": ("Config / Status line", "setting", "true"),
        "permissions": ("Config / Permissions", "setting", "default"),
        "status": ("Status", "tab", "collapsed"),
        "session": ("Status / Session", "setting", "active"),
        "runtime": ("Status / Runtime", "setting", "idle"),
        "stats": ("Stats", "tab", "collapsed"),
        "overview": ("Stats / Overview", "view", "available"),
        "models": ("Stats / Models", "view", "available"),
    }


def _should_quit(event: InputEvent) -> bool:
    if event.kind == "text" and "q" in event.text.casefold():
        return True
    if event.kind == "key" and event.key in {"q", "ctrl+c"}:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
