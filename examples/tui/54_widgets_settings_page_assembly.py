from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
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
    SearchableList,
    SearchableListItem,
    SearchableListSelect,
    TabGroup,
    TabItem,
    TabPage,
    Tabs,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

LIST_LABEL_WIDTH = 42

SETTINGS_PAGE_THEME = ThemeResolver(
    defaults={
        "widget.tabs.tab": {"color": "white"},
        "widget.tabs.selected": {"bold": True, "color": "green"},
        "widget.tabs.focus": {"bold": True, "color": "cyan"},
        "widget.tabs.level0.selected_header_focus": {"bold": True, "color": "cyan"},
        "widget.tabs.level0.selected_content_focus": {"bold": True, "color": "green"},
        "widget.tabs.level1.selected_header_focus": {"bold": True, "color": "magenta"},
        "widget.tabs.level1.selected_content_focus": {"bold": True, "color": "yellow"},
        "widget.pageScaffold.separator": {"color": "bright_black"},
        "widget.pageScaffold.footer": {"color": "bright_black"},
        "widget.searchableList.search": {"color": "white"},
        "widget.searchableList.placeholder": {"color": "bright_black"},
        "widget.searchableList.box": {"color": "bright_black"},
        "widget.searchableList.header": {"color": "bright_black"},
        "widget.searchableList.item": {"color": "white"},
        "widget.searchableList.focus": {"bold": True, "color": "cyan"},
        "widget.searchableList.description": {"color": "bright_black"},
        "widget.searchableList.empty": {"color": "bright_black"},
        "widget.searchableList.overflow": {"color": "bright_black"},
        "widget.searchableList.footer": {"color": "bright_black"},
    }
)


@dataclass(slots=True)
class SettingsHeader(FocusableMixin):
    tabs: Tabs
    title: str = "Settings"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)

    def focus(self) -> None:
        self.focused = True
        self.tabs.focus()

    def blur(self) -> None:
        self.focused = False
        self.tabs.blur()

    def handle_input(self, event: Any) -> object:
        return self.tabs.handle_input(event)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        title = RenderLine(truncate_to_width(self.title, max_width=constraints.width, ellipsis=""))
        if constraints.max_height == 1:
            return RenderResult.from_lines([title], constraints=constraints)
        tabs = self.tabs.render(RenderConstraints(width=constraints.width, max_height=1))
        rows = [title, *tabs.lines]
        cursor = None
        if tabs.cursor is not None:
            cursor = CursorDeclaration(row=1, column=tabs.cursor.column)
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)


@dataclass(slots=True)
class SearchListPage(FocusableMixin):
    items: tuple[SearchableListItem, ...]
    placeholder: str
    footer_hint: str
    toggle_booleans: bool = False
    list: SearchableList = field(init=False)

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.list = self._make_list(focused=False)

    def focus(self) -> None:
        self.focused = True
        self.list.focus()

    def blur(self) -> None:
        self.focused = False
        self.list.blur()

    def editor_input_target(self) -> object | None:
        return self.list.editor_input_target()

    def handle_input(self, event: Any) -> object:
        result = self.list.handle_input(event)
        if isinstance(result, SearchableListSelect):
            return self._activate(result.key)
        return result

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return self.list.render(constraints)

    def _activate(self, key: str) -> str:
        item = next((candidate for candidate in self.items if candidate.key == key), None)
        if item is None:
            return "Unavailable"
        boolean_value = _boolean_value(item.value)
        if self.toggle_booleans and boolean_value is not None:
            next_value = "false" if boolean_value else "true"
            self.items = tuple(replace(candidate, value=next_value) if candidate.key == key else candidate for candidate in self.items)
            self.list.set_items(self.items, preserve_active_key=key)
            if self.list.focused:
                self.list.focus_list()
            return f"Toggled: {item.label} -> {next_value}"
        return f"Selected: {item.label}"

    def _make_list(self, *, focused: bool) -> SearchableList:
        return SearchableList(
            self.items,
            placeholder=self.placeholder,
            theme=SETTINGS_PAGE_THEME,
            focused=focused,
            search_box=True,
            detail_column=LIST_LABEL_WIDTH,
            column_headers=("Setting", "Value"),
            footer_hint=self.footer_hint,
        )


@dataclass(slots=True)
class StaticPage(FocusableMixin):
    lines: tuple[str, ...]

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [
            RenderLine(truncate_to_width(line, max_width=constraints.width, ellipsis=""))
            for line in self.lines[: constraints.max_height]
        ]
        return RenderResult.from_lines(rows, constraints=constraints)


@dataclass(slots=True)
class StatsPage(FocusableMixin):
    group: TabGroup = field(default_factory=lambda: _stats_group())

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)

    def focus(self) -> None:
        self.focused = True
        self.group.focus_content()

    def blur(self) -> None:
        self.focused = False
        self.group.blur()

    def editor_input_target(self) -> object | None:
        return self.group.editor_input_target()

    def handle_input(self, event: Any) -> object:
        return self.group.handle_input(event)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return self.group.render(constraints)


@dataclass(slots=True)
class SettingsAssemblyApp(FocusableMixin):
    header: SettingsHeader = field(init=False)
    bodies: dict[str, object] = field(init=False)
    scaffold: PageScaffold = field(init=False)
    status: str = "Ready"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        tabs = Tabs(
            (
                TabItem("status", "Status"),
                TabItem("config", "Config"),
                TabItem("model", "Model"),
                TabItem("usage", "Usage"),
                TabItem("stats", "Stats"),
            ),
            value="config",
            on_change=self._select_tab,
            theme=SETTINGS_PAGE_THEME,
        )
        self.header = SettingsHeader(tabs)
        self.bodies = {
            "status": StaticPage(_status_lines()),
            "config": SearchListPage(
                _config_items(),
                placeholder="Search settings...",
                footer_hint="Type to filter | Enter/down to select | Up to tabs | Esc clear",
                toggle_booleans=True,
            ),
            "model": SearchListPage(
                _model_items(),
                placeholder="Search models...",
                footer_hint="Type to filter | Enter select | Up to tabs | Esc clear",
            ),
            "usage": StaticPage(_usage_lines()),
            "stats": StatsPage(),
        }
        self.scaffold = PageScaffold(
            header=self.header,
            body=self.bodies["config"],
            footer=self._footer,
            theme=SETTINGS_PAGE_THEME,
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

    def editor_input_target(self) -> object | None:
        return self.scaffold.editor_input_target()

    def handle_input(self, event: Any) -> object:
        result = self.scaffold.handle_input(event)
        if isinstance(result, str):
            self.status = result
            return True
        return True if result is not None else None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        self._sync_tab_focus_state()
        return self.scaffold.render(constraints)

    def _select_tab(self, value: str) -> bool:
        self.scaffold.body = self.bodies[value]
        self.scaffold.focus_region = "header"
        self.status = f"Selected: {self.header.tabs.value.title()}"
        return True

    def _footer(self, context: PageScaffoldContext) -> str:
        focus_context = self._focus_context(context)
        if focus_context == "tabs":
            text = f"Tabs | {self.status} | Left/Right switch | Down content | q quit"
        elif focus_context == "settings":
            text = f"Settings | {self.status} | Up/Down move | Enter select | Space toggle | q quit"
        elif focus_context == "search":
            text = f"Search | {self.status} | type filter | Down list | Up tabs | Esc clear | q quit"
        elif focus_context == "nested-tabs":
            text = f"Nested tabs | {self.status} | Left/Right switch | Down content | q quit"
        else:
            text = f"Page | {self.status} | Up tabs | q quit"
        return text

    def _focus_context(self, context: PageScaffoldContext) -> str:
        if context.focus_region == "header":
            return "tabs"
        body = self.bodies.get(self.header.tabs.value)
        if isinstance(body, SearchListPage):
            return "settings" if body.list.focus_region == "list" else "search"
        if isinstance(body, StatsPage) and body.group.header_focused:
            return "nested-tabs"
        return "page"

    def _sync_tab_focus_state(self) -> None:
        self.header.tabs.selected_focus = "header" if self.scaffold.focus_region == "header" else "content"


def build_app() -> Tui:
    tui = Tui()
    app = SettingsAssemblyApp()
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


def _stats_group() -> TabGroup:
    return TabGroup(
        (
            TabPage("overview", "Overview", StaticPage(_stats_overview_lines())),
            TabPage("models", "Models", StaticPage(_stats_model_lines())),
        ),
        level=1,
        content_height=14,
        theme=SETTINGS_PAGE_THEME,
    )


def _config_items() -> tuple[SearchableListItem, ...]:
    return (
        SearchableListItem("model", "Current model", "Use Model tab"),
        SearchableListItem("status-line", "Status line", "true"),
        SearchableListItem("thinking-mode", "Thinking mode", "true"),
        SearchableListItem("permission-mode", "Default permission mode", "Default"),
        SearchableListItem("editor-mode", "Editor mode", "vim"),
        SearchableListItem("auto-compact", "Auto-compact", "false"),
        SearchableListItem("show-tips", "Show tips", "true"),
        SearchableListItem("reduce-motion", "Reduce motion", "false"),
        SearchableListItem("session-recap", "Session recap", "true"),
        SearchableListItem("rewind-code", "Rewind code checkpoints", "true"),
        SearchableListItem("verbose-output", "Verbose output", "true"),
        SearchableListItem("terminal-progress", "Terminal progress bar", "true"),
        SearchableListItem("turn-duration", "Show turn duration", "true"),
        SearchableListItem("gitignore-picker", "Respect .gitignore in file picker", "true"),
        SearchableListItem("skip-copy-picker", "Skip the copy picker", "false"),
        SearchableListItem("auto-update", "Auto-update channel", "disabled"),
        SearchableListItem("theme", "Theme", "Dark mode"),
        SearchableListItem("notifications", "Local notifications", "Auto"),
        SearchableListItem("output-style", "Output style", "default"),
        SearchableListItem("language", "Language", "Default English"),
        SearchableListItem("show-pr-footer", "Show PR status footer", "true"),
        SearchableListItem("checkpoint-limit", "Checkpoint limit", "24"),
        SearchableListItem("terminal-title", "Terminal title", "session name"),
        SearchableListItem("history-limit", "History limit", "200"),
        SearchableListItem("diff-context", "Diff context lines", "3"),
        SearchableListItem("inline-images", "Inline images", "auto"),
        SearchableListItem("copy-mode", "Copy mode", "clipboard"),
        SearchableListItem("paste-bracketed", "Bracketed paste", "true"),
        SearchableListItem("shell-integration", "Shell integration", "auto"),
        SearchableListItem("diagnostics", "Diagnostics", "compact"),
    )


def _model_items() -> tuple[SearchableListItem, ...]:
    return (
        SearchableListItem("current", "Current model", "kimi-for-coding"),
        SearchableListItem("coding", "Coding profile", "kimi-for-coding"),
        SearchableListItem("planner", "Planner profile", "kimi-k2.5"),
        SearchableListItem("quick", "Quick profile", "Haiku 4.5"),
        SearchableListItem("fallback", "Fallback model", "Haiku 4.5"),
        SearchableListItem("temperature", "Temperature", "0.2"),
        SearchableListItem("reasoning", "Reasoning mode", "auto"),
        SearchableListItem("context", "Context budget", "large"),
        SearchableListItem("routing", "Routing policy", "task aware"),
        SearchableListItem("local", "Local model", "disabled"),
        SearchableListItem("cloud", "Cloud model", "enabled"),
        SearchableListItem("cache", "Prompt cache", "enabled"),
    )


def _status_lines() -> tuple[str, ...]:
    return (
        "Status",
        "",
        "Workspace: tui",
        "Permission mode: Default",
        "Status line: on",
        "Terminal progress: on",
    )


def _usage_lines() -> tuple[str, ...]:
    return (
        "Usage",
        "",
        "All time | Last 7 days | Last 30 days",
        "",
        "Total tokens: 178.5m",
        "Sessions: 47",
        "Active days: 17/88",
        "Current streak: 0 days",
    )


def _stats_overview_lines() -> tuple[str, ...]:
    return (
        "Tokens per Day",
        "145.7M +--+",
        "127.5M |  |",
        "109.3M |  |",
        " 91.1M |  |",
        " 72.9M |  |",
        " 54.6M |  |",
        " 36.4M |  |",
        " 18.2M |  +-----+",
        "    0 +------------------------------",
        "       Mar 15       May 3        Jun 9",
    )


def _stats_model_lines() -> tuple[str, ...]:
    return (
        "Model usage",
        "",
        "kimi-k2.5          82.7%   In: 146.9m  Out: 655.0k",
        "kimi-for-coding    17.2%   In: 30.1m   Out: 671.9k",
        "Haiku 4.5           0.1%   In: 162.8k  Out: 1.5k",
    )


def _boolean_value(value: str) -> bool | None:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _should_quit(event: InputEvent) -> bool:
    if event.kind == "text" and "q" in event.text.casefold():
        return True
    if event.kind == "key" and event.key in {"q", "ctrl+c"}:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
