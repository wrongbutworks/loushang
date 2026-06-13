from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any

from loushang.tui import (
    CursorDeclaration,
    FocusableMixin,
    InputEvent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    SearchableList,
    SearchableListItem,
    SearchableListSelect,
    TabGroup,
    TabPage,
    ThemeResolver,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)

CONTENT_HEIGHT = 20
SETTING_LABEL_WIDTH = 42

TABGROUP_SEARCH_THEME = ThemeResolver(
    defaults={
        "widget.tabs.tab": {"color": "white"},
        "widget.tabs.level0.selected_header_focus": {"bold": True, "color": "cyan"},
        "widget.tabs.level0.selected_content_focus": {"bold": True, "color": "green"},
        "widget.tabs.level1.selected_header_focus": {"bold": True, "color": "magenta"},
        "widget.tabs.level1.selected_content_focus": {"bold": True, "color": "yellow"},
        "widget.searchableList.search": {"color": "white"},
        "widget.searchableList.placeholder": {"color": "bright_black"},
        "widget.searchableList.item": {"color": "white"},
        "widget.searchableList.focus": {"bold": True, "color": "cyan"},
        "widget.searchableList.disabled": {"dim": True},
        "widget.searchableList.description": {"color": "bright_black"},
        "widget.searchableList.empty": {"color": "bright_black"},
        "widget.searchableList.overflow": {"color": "bright_black"},
    }
)


@dataclass(slots=True)
class SettingsListPage(FocusableMixin):
    items: tuple[SearchableListItem, ...] = field(default_factory=lambda: _settings_items())
    settings: SearchableList = field(init=False)

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.settings = self._make_settings(focused=False)

    def focus(self) -> None:
        self.focused = True
        self.settings.focus()

    def blur(self) -> None:
        self.focused = False
        self.settings.blur()

    def editor_input_target(self) -> object | None:
        return self.settings.editor_input_target()

    def handle_input(self, event: Any) -> object:
        if getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"enter", "space"}:
            return self._activate_current()
        if getattr(event, "kind", "") == "text" and getattr(event, "text", "") == " ":
            return self._activate_current()
        return self.settings.handle_input(event)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if constraints.max_height <= 2:
            return self.settings.render(constraints)
        settings = self.settings.render(
            RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2))
        )
        rows = list(settings.lines[:1])
        rows.append(RenderLine(_separator(constraints.width)))
        rows.append(RenderLine(_settings_header(constraints.width)))
        rows.extend(settings.lines[1:])
        return RenderResult.from_lines(
            rows[: constraints.max_height],
            constraints=constraints,
            cursor=settings.cursor,
        )

    def _activate_current(self) -> str | None:
        item = self.settings.active_item
        if item is None:
            return "Unavailable"
        boolean_value = _boolean_value(item.value)
        if boolean_value is None:
            return f"Selected: {item.label}"
        next_value = "false" if boolean_value else "true"
        self.items = tuple(replace(existing, value=next_value) if existing.key == item.key else existing for existing in self.items)
        query = self.settings.query
        focus_region = self.settings.focus_region
        focused = self.settings.focused
        self.settings = self._make_settings(query=query, focus_region=focus_region, focused=focused)
        return f"Toggled: {item.label} -> {next_value}"

    def _make_settings(
        self,
        *,
        query: str = "",
        focus_region: str = "search",
        focused: bool,
    ) -> SearchableList:
        return SearchableList(
            self.items,
            query=query,
            focus_region=focus_region,
            placeholder="Search settings...",
            theme=TABGROUP_SEARCH_THEME,
            focused=focused,
        )


@dataclass(slots=True)
class StaticPage:
    lines: tuple[str, ...]

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [
            RenderLine(truncate_to_width(line, max_width=constraints.width, ellipsis=""))
            for line in self.lines[: constraints.max_height]
        ]
        return RenderResult.from_lines(rows, constraints=constraints)


@dataclass(slots=True)
class SettingsPanelsApp(FocusableMixin):
    tabs: TabGroup = field(default_factory=lambda: TabGroup(_top_pages(), content_height=CONTENT_HEIGHT))
    status: str = "Ready"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.focus()

    def focus(self) -> None:
        self.focused = True
        self.tabs.focus_content()

    def blur(self) -> None:
        self.focused = False
        self.tabs.blur()

    def editor_input_target(self) -> object | None:
        return self.tabs.editor_input_target()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        body_height = max(1, min(constraints.max_height - 2, CONTENT_HEIGHT + 2))
        group_height = max(1, body_height - 1)
        group = self.tabs.render(RenderConstraints(width=constraints.width, max_height=group_height))
        rows = _with_top_separator(group.lines, width=constraints.width)
        cursor = _offset_cursor_after_top_separator(group.cursor)
        while len(rows) < body_height:
            rows.append(RenderLine(""))
        if len(rows) < constraints.max_height:
            rows.append(RenderLine(_separator(constraints.width)))
        if len(rows) < constraints.max_height:
            rows.append(RenderLine(_footer_text(self.status, width=constraints.width)))
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

    def handle_input(self, event: Any) -> object:
        result = self.tabs.handle_input(event)
        if isinstance(result, SearchableListSelect):
            self.status = f"Selected: {result.label}"
            return True
        if isinstance(result, str):
            self.status = result
            return True
        return True if result is not None else None


def build_app() -> Tui:
    tui = Tui()
    app = SettingsPanelsApp()
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


def _top_pages() -> tuple[TabPage, ...]:
    return (
        TabPage("workspace", "Workspace", SettingsListPage()),
        TabPage("models", "Models", StaticPage(_model_lines())),
        TabPage("permissions", "Permissions", StaticPage(_permission_lines())),
        TabPage("activity", "Activity", _activity_tabs()),
    )


def _activity_tabs() -> TabGroup:
    return TabGroup(
        (
            TabPage("overview", "Overview", StaticPage(_activity_overview_lines())),
            TabPage("models", "Models", StaticPage(_activity_model_lines())),
        ),
        level=1,
        content_height=CONTENT_HEIGHT - 1,
        theme=TABGROUP_SEARCH_THEME,
    )


def _settings_items() -> tuple[SearchableListItem, ...]:
    base = (
        SearchableListItem("model", "Model", "kimi-for-coding"),
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
        SearchableListItem("archive", "Archive old sessions", "disabled", disabled=True),
    )
    return base


def _boolean_value(value: str) -> bool | None:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _separator(width: int) -> str:
    return "-" * max(1, width)


def _settings_header(width: int) -> str:
    label_width = max(8, min(SETTING_LABEL_WIDTH, width - 8))
    text = f"{'Setting':<{label_width}}Value"
    return truncate_to_width(text, max_width=width, ellipsis="")


def _with_top_separator(lines: tuple[RenderLine, ...], *, width: int) -> list[RenderLine]:
    if not lines:
        return []
    return [lines[0], RenderLine(_separator(width)), *lines[1:]]


def _offset_cursor_after_top_separator(cursor: CursorDeclaration | None) -> CursorDeclaration | None:
    if cursor is None:
        return None
    if cursor.row == 0:
        return cursor
    return CursorDeclaration(row=cursor.row + 1, column=cursor.column)


def _footer_text(status: str, *, width: int) -> str:
    text = f"{status} | Type to filter | Enter select/toggle | Space toggle | Esc clear | q quit"
    return truncate_to_width(text, max_width=width, ellipsis="")


def _should_quit(event: InputEvent) -> bool:
    if event.kind == "text" and "q" in event.text.casefold():
        return True
    if event.kind == "key" and event.key in {"q", "ctrl+c"}:
        return True
    return False


def _model_lines() -> tuple[str, ...]:
    return (
        "Model configuration",
        "",
        "Favorite model: kimi-k2.5",
        "Current model: kimi-for-coding",
        "Fallback model: Haiku 4.5",
        "",
        "Routing",
        "coding tasks        kimi-for-coding",
        "planning tasks      kimi-k2.5",
        "quick summaries     Haiku 4.5",
    )


def _permission_lines() -> tuple[str, ...]:
    return (
        "Permission modes",
        "",
        "Default             Ask before writes outside workspace",
        "Read only           Inspect files without edits",
        "Auto apply          Workspace writes without prompt",
        "",
        "Current mode: Default",
    )


def _activity_overview_lines() -> tuple[str, ...]:
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
        "",
        "All time | Last 7 days | Last 30 days",
        "Sessions: 47",
        "Active days: 17/88",
    )


def _activity_model_lines() -> tuple[str, ...]:
    return (
        "Model usage",
        "",
        "kimi-k2.5          82.7%   In: 146.9m  Out: 655.0k",
        "kimi-for-coding    17.2%   In: 30.1m   Out: 671.9k",
        "Haiku 4.5           0.1%   In: 162.8k  Out: 1.5k",
        "",
        "All time | Last 7 days | Last 30 days",
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
