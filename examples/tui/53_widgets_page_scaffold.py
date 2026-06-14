from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loushang.tui import (
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
    TabItem,
    Tabs,
    Tui,
    TuiInputResult,
    TuiRunner,
    truncate_to_width,
)


@dataclass(slots=True)
class PageScaffoldDemo(FocusableMixin):
    tabs: Tabs = field(init=False)
    bodies: dict[str, object] = field(init=False)
    scaffold: PageScaffold = field(init=False)
    status: str = "Ready"

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)
        self.tabs = Tabs(
            (
                TabItem("config", "Config"),
                TabItem("models", "Models"),
                TabItem("activity", "Activity"),
            ),
            on_change=self._select_tab,
        )
        self.bodies = {
            "config": _searchable_page("Search settings...", _config_items()),
            "models": _searchable_page("Search models...", _model_items()),
            "activity": StaticLinesPage(
                (
                    "Activity",
                    "",
                    "Recent actions",
                    "Build succeeded",
                    "Tests passed",
                    "Plan reviewed",
                )
            ),
        }
        self.scaffold = PageScaffold(
            header=self.tabs,
            body=self.bodies[self.tabs.value],
            footer=self._footer,
            focused=True,
            focus_region="body",
            separator_after_header=True,
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

    def render(self, constraints: RenderConstraints) -> RenderResult:
        self._sync_tab_focus_state()
        return self.scaffold.render(constraints)

    def handle_input(self, event: Any) -> object:
        result = self.scaffold.handle_input(event)
        if isinstance(result, SearchableListSelect):
            self.status = f"Selected: {result.label}"
            return True
        return True if result is not None else None

    def _select_tab(self, value: str) -> bool:
        self.scaffold.body = self.bodies[value]
        self.scaffold.focus_region = "header"
        self.status = f"Selected: {value}"
        return True

    def _footer(self, context: PageScaffoldContext) -> str:
        if context.focus_region == "header":
            text = f"Header | {self.status} | Left/Right switch | Down/Enter body | q quit"
        else:
            text = f"Body | {self.status} | Type filter | Down list | Up tabs | Enter select | q quit"
        return text

    def _sync_tab_focus_state(self) -> None:
        self.tabs.selected_focus = "header" if self.scaffold.focus_region == "header" else "content"


@dataclass(slots=True)
class StaticLinesPage(FocusableMixin):
    lines: tuple[str, ...]

    def __post_init__(self) -> None:
        FocusableMixin.__init__(self)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [
            RenderLine(truncate_to_width(line, max_width=constraints.width, ellipsis=""))
            for line in self.lines[: constraints.max_height]
        ]
        return RenderResult.from_lines(rows, constraints=constraints)


def build_app() -> Tui:
    tui = Tui()
    app = PageScaffoldDemo()
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


def _searchable_page(placeholder: str, items: tuple[SearchableListItem, ...]) -> SearchableList:
    return SearchableList(
        items,
        placeholder=placeholder,
        search_box=True,
        detail_column=34,
    )


def _should_quit(event: InputEvent) -> bool:
    if event.kind == "text" and "q" in event.text.casefold():
        return True
    if event.kind == "key" and event.key in {"q", "ctrl+c"}:
        return True
    return False


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
        SearchableListItem("kimi-k2.5", "kimi-k2.5", "82.7%"),
        SearchableListItem("kimi-for-coding", "kimi-for-coding", "17.2%"),
        SearchableListItem("haiku-4.5", "Haiku 4.5", "0.1%"),
        SearchableListItem("planner", "Planner profile", "kimi-k2.5"),
        SearchableListItem("coding", "Coding profile", "kimi-for-coding"),
        SearchableListItem("quick", "Quick profile", "Haiku 4.5"),
        SearchableListItem("fallback", "Fallback model", "Haiku 4.5"),
        SearchableListItem("temperature", "Temperature", "0.2"),
        SearchableListItem("reasoning", "Reasoning mode", "auto"),
        SearchableListItem("context", "Context budget", "large"),
        SearchableListItem("usage", "Usage window", "30 days"),
        SearchableListItem("routing", "Routing policy", "task aware"),
        SearchableListItem("local", "Local model", "disabled"),
        SearchableListItem("cloud", "Cloud model", "enabled"),
        SearchableListItem("cache", "Prompt cache", "enabled"),
        SearchableListItem("tools", "Tool calling", "enabled"),
        SearchableListItem("vision", "Vision", "auto"),
        SearchableListItem("audio", "Audio", "disabled"),
        SearchableListItem("batch", "Batch mode", "disabled"),
        SearchableListItem("limits", "Rate limit", "standard"),
        SearchableListItem("audit", "Audit logging", "compact"),
        SearchableListItem("experiments", "Experiments", "off"),
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
