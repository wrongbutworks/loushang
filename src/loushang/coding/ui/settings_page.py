from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loushang.coding.ui.model_list import (
    ModelChoice,
    available_model_choices,
    current_model_choice_value,
    select_available_model,
)
from loushang.coding.ui.status_line import (
    StatusLinePreviewSnapshot,
    StatusLineSettings,
    status_line_fields,
    status_line_separator,
    status_line_style_mode,
)
from loushang.coding.ui.status_provider import CodingTuiStatusProvider, StatusSnapshot
from loushang.tui import (
    CursorDeclaration,
    InputEvent,
    InputIntent,
    RenderConstraints,
    RenderLine,
    RenderResult,
    SearchableList,
    SearchableListItem,
    SearchableListSelect,
    StatusBar,
    TabGroup,
    TabPage,
    ThemeResolver,
    truncate_to_width,
)

__all__ = [
    "ConfigRow",
    "ConfigSettingsPage",
    "ModelPage",
    "SettingsApplyResult",
    "SettingsPageView",
]


@dataclass(frozen=True, slots=True)
class SettingsApplyResult:
    message: str
    statusline_visible: bool | None = None
    statusline_settings: StatusLineSettings | None = None
    refresh_model_label: bool = False


@dataclass(frozen=True, slots=True)
class ConfigRow:
    id: str
    label: str
    value: str
    description: str = ""
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class _ManagerBoolConfig:
    id: str
    label: str
    getter: str
    setter: str
    status_label: str


SETTINGS_VALUE_COLUMN = 42

SETTINGS_PAGE_THEME = ThemeResolver(
    defaults={
        "widget.tabs.tab": {"color": "white"},
        "widget.tabs.selected": {"bold": True, "color": "green"},
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

_MANAGER_BOOL_CONFIGS = (
    _ManagerBoolConfig(
        "terminal.progress",
        "Terminal progress",
        "get_show_terminal_progress",
        "set_show_terminal_progress",
        "Terminal progress",
    ),
    _ManagerBoolConfig(
        "terminal.show_images",
        "Show images",
        "get_show_images",
        "set_show_images",
        "Show images",
    ),
    _ManagerBoolConfig(
        "terminal.clear_on_shrink",
        "Clear on shrink",
        "get_clear_on_shrink",
        "set_clear_on_shrink",
        "Clear on shrink",
    ),
    _ManagerBoolConfig(
        "images.auto_resize",
        "Image auto-resize",
        "get_image_auto_resize",
        "set_image_auto_resize",
        "Image auto-resize",
    ),
    _ManagerBoolConfig(
        "images.block_images",
        "Block images",
        "get_block_images",
        "set_block_images",
        "Block images",
    ),
    _ManagerBoolConfig(
        "retry.enabled",
        "Retry",
        "get_retry_enabled",
        "set_retry_enabled",
        "Retry",
    ),
)


@dataclass(slots=True)
class StaticLinesPage:
    lines: tuple[str, ...]
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"left", "right", "home", "end"}:
            return True
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        rows = [
            RenderLine(truncate_to_width(line, max_width=constraints.width, ellipsis=""))
            for line in self.lines[: constraints.max_height]
        ]
        return RenderResult.from_lines(rows, constraints=constraints)


@dataclass(slots=True)
class ConfigSettingsPage:
    rows: tuple[ConfigRow, ...]
    focused: bool = False
    settings: SearchableList = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self._make_list(focused=False)

    def focus(self) -> None:
        self.focused = True
        self.settings.focus()

    def blur(self) -> None:
        self.focused = False
        self.settings.blur()

    def editor_input_target(self) -> object | None:
        return self.settings.editor_input_target()

    def set_rows(self, rows: tuple[ConfigRow, ...], *, preserve_active_key: str = "") -> None:
        self.rows = rows
        self.settings.set_items(_config_items(rows), preserve_active_key=preserve_active_key)

    def handle_input(self, event: object) -> object:
        result = self.settings.handle_input(event)
        if isinstance(result, SearchableListSelect):
            return self._setting_intent(result.key)
        if result is not None:
            return result
        if self.settings.focus_region == "list" and _is_space_event(event):
            item = self.settings.active_item
            if item is not None:
                return self._setting_intent(item.key)
        if _is_tab_fallback_key(event):
            return True
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        if constraints.max_height <= 4:
            return self.settings.render(constraints)
        result = self.settings.render(
            RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 2))
        )
        header = RenderLine(_settings_header(constraints.width))
        rows = [*result.lines[:3], RenderLine(""), header, *result.lines[3:]]
        cursor = result.cursor
        if cursor is not None and cursor.row >= 3:
            cursor = CursorDeclaration(row=cursor.row + 2, column=cursor.column)
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

    def _make_list(self, *, focused: bool) -> SearchableList:
        return SearchableList(
            _config_items(self.rows),
            placeholder="Search settings...",
            empty_text="No matching settings",
            focused=focused,
            search_box=True,
            detail_column=SETTINGS_VALUE_COLUMN,
            theme=SETTINGS_PAGE_THEME,
        )

    def _setting_intent(self, key: str) -> InputIntent | None:
        row = _row_for_key(self.rows, key)
        if row is None or row.disabled:
            return None
        value = _next_value(row.value)
        return InputIntent(kind="setting", text=row.id, note=value)


@dataclass(slots=True)
class StatusLineSettingsPage:
    statusline_settings: StatusLineSettings
    statusline_preview: Callable[[], StatusLinePreviewSnapshot]
    focused: bool = False
    settings: SearchableList = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self._make_list(focused=False)

    def focus(self) -> None:
        self.focused = True
        self.settings.focus()

    def blur(self) -> None:
        self.focused = False
        self.settings.blur()

    def editor_input_target(self) -> object | None:
        return self.settings.editor_input_target()

    def set_statusline_settings(self, settings: StatusLineSettings, *, preserve_active_key: str = "") -> None:
        self.statusline_settings = settings
        self.settings.set_items(_config_items(_statusline_rows(settings)), preserve_active_key=preserve_active_key)

    def handle_input(self, event: object) -> object:
        result = self.settings.handle_input(event)
        if isinstance(result, SearchableListSelect):
            return self._setting_intent(result.key)
        if result is not None:
            return result
        if self.settings.focus_region == "list" and _is_space_event(event):
            item = self.settings.active_item
            if item is not None:
                return self._setting_intent(item.key)
        if _is_tab_fallback_key(event):
            return True
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        if constraints.max_height <= 6:
            return self.settings.render(constraints)
        result = self.settings.render(
            RenderConstraints(width=constraints.width, max_height=max(1, constraints.max_height - 4))
        )
        header = RenderLine(_settings_header(constraints.width))
        preview = _statusline_preview_lines(
            self.statusline_preview(),
            self.statusline_settings,
            width=constraints.width,
        )
        rows = [*result.lines[:3], RenderLine(""), header, *result.lines[3:], RenderLine(""), *preview]
        cursor = result.cursor
        if cursor is not None and cursor.row >= 3:
            cursor = CursorDeclaration(row=cursor.row + 2, column=cursor.column)
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

    def _make_list(self, *, focused: bool) -> SearchableList:
        return SearchableList(
            _config_items(_statusline_rows(self.statusline_settings)),
            placeholder="Search status line...",
            empty_text="No matching status line settings",
            focused=focused,
            search_box=True,
            detail_column=SETTINGS_VALUE_COLUMN,
            theme=SETTINGS_PAGE_THEME,
        )

    def _setting_intent(self, key: str) -> InputIntent | None:
        row = _row_for_key(_statusline_rows(self.statusline_settings), key)
        if row is None or row.disabled:
            return None
        return InputIntent(kind="setting", text=row.id, note=_next_statusline_value(row.id, row.value))


@dataclass(slots=True)
class ModelPage:
    choices: tuple[ModelChoice, ...]
    current_value: str | None = None
    error: str = ""
    focused: bool = False
    models: SearchableList = field(init=False)

    def __post_init__(self) -> None:
        self.models = self._make_list(focused=False)

    @property
    def unavailable(self) -> bool:
        return bool(self.error) or not self.choices

    def focus(self) -> None:
        self.focused = True
        self.models.focus()

    def blur(self) -> None:
        self.focused = False
        self.models.blur()

    def editor_input_target(self) -> object | None:
        if self.unavailable:
            return None
        return self.models.editor_input_target()

    def set_choices(self, choices: tuple[ModelChoice, ...], *, current_value: str | None, error: str = "") -> None:
        self.choices = choices
        self.current_value = current_value
        self.error = error
        self.models.set_items(_model_items(choices, current_value=current_value), preserve_active_key=current_value or "")

    def handle_input(self, event: object) -> object:
        if self.unavailable:
            return True if _is_tab_fallback_key(event) else None
        result = self.models.handle_input(event)
        if isinstance(result, SearchableListSelect):
            return InputIntent(kind="setting", text="model.current", note=result.key)
        if result is not None:
            return result
        if self.models.focus_region == "list" and _is_space_event(event):
            item = self.models.active_item
            if item is not None:
                return InputIntent(kind="setting", text="model.current", note=item.key)
        if _is_tab_fallback_key(event):
            return True
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if self.unavailable:
            lines = ("Model selection unavailable", self.error or "No models available.")
            return StaticLinesPage(lines).render(constraints)
        return self.models.render(constraints)

    def _make_list(self, *, focused: bool) -> SearchableList:
        return SearchableList(
            _model_items(self.choices, current_value=self.current_value),
            placeholder="Search models...",
            empty_text="No matching models",
            focused=focused,
            search_box=True,
            detail_column=SETTINGS_VALUE_COLUMN,
            theme=SETTINGS_PAGE_THEME,
        )


@dataclass(slots=True)
class SettingsPageView:
    session: Any
    status_provider: CodingTuiStatusProvider
    settings_manager: object | None = None
    usage_provider: Callable[[], object | None] | None = None
    status_page: StaticLinesPage = field(init=False)
    config_page: ConfigSettingsPage = field(init=False)
    model_page: ModelPage = field(init=False)
    statusline_page: StatusLineSettingsPage = field(init=False)
    usage_page: StaticLinesPage = field(init=False)
    stats_page: TabGroup = field(init=False)
    tabs: TabGroup = field(init=False)
    focused: bool = field(default=False, init=False)
    statusline_preview: Callable[[], StatusLinePreviewSnapshot] | None = None

    @classmethod
    async def create(
        cls,
        *,
        session: Any,
        status_provider: CodingTuiStatusProvider,
        usage_provider: Callable[[], object | None] | None = None,
        settings_manager: object | None = None,
        session_settings: object | None = None,
        statusline_preview: Callable[[], StatusLinePreviewSnapshot] | None = None,
    ) -> SettingsPageView:
        del session_settings
        view = cls(
            session=session,
            status_provider=status_provider,
            settings_manager=settings_manager,
            usage_provider=usage_provider,
            statusline_preview=statusline_preview,
        )
        await view._build()
        view.focus()
        return view

    async def apply_setting(self, item_id: str, value: str) -> SettingsApplyResult:
        if item_id == "statusline" or item_id.startswith("statusline."):
            message = self.status_provider.apply_statusline_setting(item_id, value)
            self._refresh_status_page()
            self._refresh_statusline_page(preserve_active_key=item_id)
            settings = self.status_provider.statusline_settings()
            return SettingsApplyResult(
                message,
                statusline_visible=settings.enabled,
                statusline_settings=settings,
            )
        config = _manager_bool_config(item_id)
        if config is not None:
            enabled = _as_bool(value)
            if enabled is None:
                return SettingsApplyResult(f"Invalid {config.label} value.")
            setter = getattr(self.settings_manager, config.setter, None)
            if not callable(setter):
                return SettingsApplyResult(f"{config.status_label} is not available.")
            setter(enabled)
            self._refresh_config_rows(preserve_active_key=config.id)
            return SettingsApplyResult(f"{config.status_label}: {'on' if enabled else 'off'}")
        if item_id == "model.current":
            message = await select_available_model(self.session, query=value)
            await self._refresh_model_page()
            self._refresh_status_page()
            return SettingsApplyResult(message, refresh_model_label=True)
        return SettingsApplyResult(f"Unknown setting: {item_id}")

    def focus(self) -> None:
        self.focused = True
        self.tabs.focus_content()

    def blur(self) -> None:
        self.focused = False
        self.tabs.blur()

    def editor_input_target(self) -> object | None:
        return self.tabs.editor_input_target()

    def handle_input(self, event: InputEvent) -> object:
        result = self.tabs.handle_input(event)
        if result is not None:
            return result
        if _is_escape_event(event):
            return InputIntent(kind="surface_close")
        if _is_q_event(event) and self._focus_context() in {"tabs", "page", "settings-list", "model-list"}:
            return InputIntent(kind="surface_close")
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)
        body_height = max(1, constraints.max_height - 2)
        result = self.tabs.render(RenderConstraints(width=constraints.width, max_height=body_height))
        rows = _with_separator(result.lines, width=constraints.width)
        cursor = _offset_cursor_after_separator(result.cursor)
        footer = _footer_text(self._focus_context(), width=constraints.width)
        while len(rows) < constraints.max_height - 1:
            rows.append(RenderLine(""))
        if len(rows) < constraints.max_height:
            rows.append(RenderLine(footer))
        return RenderResult.from_lines(rows[: constraints.max_height], constraints=constraints, cursor=cursor)

    async def _build(self) -> None:
        self.status_page = StaticLinesPage(_status_lines(self.status_provider.snapshot()))
        self.config_page = ConfigSettingsPage(_config_rows(self.status_provider, self.settings_manager))
        choices, current_value, error = await _load_model_choices(self.session)
        self.model_page = ModelPage(choices, current_value=current_value, error=error)
        self.statusline_page = StatusLineSettingsPage(
            self.status_provider.statusline_settings(),
            self._statusline_preview_snapshot,
        )
        self.usage_page = StaticLinesPage(_usage_lines(self.usage_provider))
        self.stats_page = TabGroup(
            (
                TabPage("overview", "Overview", StaticLinesPage(_stats_overview_lines(self.status_provider.snapshot()))),
                TabPage("model-usage", "Model Usage", StaticLinesPage(_model_usage_lines(current_value))),
            ),
            value="overview",
            level=1,
            theme=SETTINGS_PAGE_THEME,
        )
        self.tabs = TabGroup(
            (
                TabPage("status", "Status", self.status_page),
                TabPage("config", "Config", self.config_page),
                TabPage("model", "Model", self.model_page),
                TabPage("status-line", "Status Line", self.statusline_page),
                TabPage("usage", "Usage", self.usage_page),
                TabPage("stats", "Stats", self.stats_page),
            ),
            value="config",
            theme=SETTINGS_PAGE_THEME,
        )

    def _refresh_status_page(self) -> None:
        self.status_page.lines = _status_lines(self.status_provider.snapshot())

    def _refresh_config_rows(self, *, preserve_active_key: str = "") -> None:
        self.config_page.set_rows(_config_rows(self.status_provider, self.settings_manager), preserve_active_key=preserve_active_key)

    def _refresh_statusline_page(self, *, preserve_active_key: str = "") -> None:
        self.statusline_page.set_statusline_settings(
            self.status_provider.statusline_settings(),
            preserve_active_key=preserve_active_key,
        )

    async def _refresh_model_page(self) -> None:
        choices, current_value, error = await _load_model_choices(self.session)
        self.model_page.set_choices(choices, current_value=current_value, error=error)
        selected = self.stats_page.selected_page
        if selected is not None and isinstance(selected.content, StaticLinesPage):
            selected.content.lines = _model_usage_lines(current_value)

    def _focus_context(self) -> str:
        if self.tabs.header_focused:
            return "tabs"
        page = self.tabs.selected_page
        content = page.content if page is not None else None
        if isinstance(content, ConfigSettingsPage):
            return "search" if content.settings.focus_region == "search" else "settings-list"
        if isinstance(content, StatusLineSettingsPage):
            return "search" if content.settings.focus_region == "search" else "settings-list"
        if isinstance(content, ModelPage):
            return "search" if content.models.focus_region == "search" else "model-list"
        if isinstance(content, TabGroup):
            return "tabs" if content.header_focused else "page"
        return "page"

    def _statusline_preview_snapshot(self) -> StatusLinePreviewSnapshot:
        if self.statusline_preview is not None:
            return self.statusline_preview()
        snapshot = self.status_provider.snapshot()
        return StatusLinePreviewSnapshot(
            model_label=snapshot.model_label,
            cwd=snapshot.cwd,
            branch=snapshot.branch,
            session_label=snapshot.session_label,
            running=snapshot.running,
        )


async def _load_model_choices(session: Any) -> tuple[tuple[ModelChoice, ...], str | None, str]:
    try:
        choices = await available_model_choices(session)
        current_value = await current_model_choice_value(session, choices=choices)
    except Exception as error:
        return (), None, str(error)
    return tuple(choices), current_value, ""


def _config_rows(_status_provider: CodingTuiStatusProvider, settings_manager: object | None) -> tuple[ConfigRow, ...]:
    rows = []
    if settings_manager is not None:
        for config in _MANAGER_BOOL_CONFIGS:
            getter = getattr(settings_manager, config.getter, None)
            if callable(getter):
                rows.append(ConfigRow(config.id, config.label, _bool_text(bool(getter()))))
    return tuple(rows)


def _statusline_rows(settings: StatusLineSettings) -> tuple[ConfigRow, ...]:
    return (
        ConfigRow("statusline.enabled", "Enabled", _bool_text(settings.enabled)),
        ConfigRow("statusline.field.model", "Model", _bool_text(settings.model)),
        ConfigRow("statusline.field.workspace", "Workspace", _bool_text(settings.workspace)),
        ConfigRow("statusline.field.branch", "Branch", _bool_text(settings.branch)),
        ConfigRow("statusline.field.session", "Session", _bool_text(settings.session)),
        ConfigRow("statusline.field.runtime", "Runtime", _bool_text(settings.runtime)),
        ConfigRow("statusline.field.queue", "Queue", settings.queue),
        ConfigRow("statusline.field.message", "Message", settings.message),
        ConfigRow("statusline.separator", "Separator", settings.separator),
        ConfigRow("statusline.style", "Style", settings.style),
    )


def _config_items(rows: tuple[ConfigRow, ...]) -> tuple[SearchableListItem, ...]:
    return tuple(
        SearchableListItem(row.id, row.label, row.value, row.description, disabled=row.disabled)
        for row in rows
    )


def _model_items(choices: tuple[ModelChoice, ...], *, current_value: str | None) -> tuple[SearchableListItem, ...]:
    return tuple(
        SearchableListItem(
            choice.value,
            choice.label,
            "current" if choice.value == current_value else "",
            choice.description,
        )
        for choice in choices
    )


def _row_for_key(rows: tuple[ConfigRow, ...], key: str) -> ConfigRow | None:
    for row in rows:
        if row.id == key:
            return row
    return None


def _status_lines(snapshot: StatusSnapshot) -> tuple[str, ...]:
    return (
        "Status",
        "",
        f"Model              {snapshot.model_label or 'Unavailable'}",
        f"Workspace          {snapshot.cwd}",
        f"Branch             {snapshot.branch or 'Unavailable'}",
        f"Session            {snapshot.session_label or 'Unavailable'}",
        f"Thinking           {snapshot.thinking_level or 'Unavailable'}",
        f"Runtime            {'running' if snapshot.running else 'idle'}",
        f"Status line        {_bool_text(snapshot.statusline_visible)}",
    )


def _usage_lines(provider: Callable[[], object | None] | None) -> tuple[str, ...]:
    if provider is None:
        return ("Usage", "", "Usage data unavailable")
    try:
        snapshot = provider()
    except Exception:
        snapshot = None
    if snapshot is None:
        return ("Usage", "", "Usage data unavailable")
    return (
        "Usage",
        "",
        f"Current context    {getattr(snapshot, 'tokens', 'Unavailable')}",
        f"Context window     {getattr(snapshot, 'context_window', 'Unavailable')}",
        f"Percent used       {getattr(snapshot, 'percent', 'Unavailable')}",
        f"Source             {getattr(snapshot, 'source', 'Unavailable')}",
    )


def _stats_overview_lines(snapshot: StatusSnapshot) -> tuple[str, ...]:
    return (
        "Session Overview",
        "",
        f"Session            {snapshot.session_label or 'Unavailable'}",
        f"Runtime            {'running' if snapshot.running else 'idle'}",
        "Historical stats   Unavailable",
    )


def _model_usage_lines(current_value: str | None) -> tuple[str, ...]:
    return (
        "Model Usage",
        "",
        f"Current model      {current_value or 'Unavailable'}",
        "Historical usage   Unavailable",
    )


def _statusline_preview_lines(
    snapshot: StatusLinePreviewSnapshot,
    settings: StatusLineSettings,
    *,
    width: int,
) -> tuple[RenderLine, ...]:
    result = StatusBar(
        status_line_fields(snapshot, settings),
        separator=status_line_separator(settings),
        style_mode=status_line_style_mode(settings),
    ).render(RenderConstraints(width=width, max_height=1))
    line = result.lines[0].text if result.lines else ""
    return (RenderLine("Preview"), RenderLine(line))


def _settings_header(width: int) -> str:
    value_column = max(8, min(SETTINGS_VALUE_COLUMN, max(8, width - 8)))
    return truncate_to_width(f"{'Setting':<{value_column}}Value", max_width=width, ellipsis="")


def _separator(width: int) -> str:
    return "-" * max(1, width)


def _with_separator(lines: tuple[RenderLine, ...], *, width: int) -> list[RenderLine]:
    if not lines:
        return []
    return [lines[0], RenderLine(_separator(width)), *lines[1:]]


def _offset_cursor_after_separator(cursor: CursorDeclaration | None) -> CursorDeclaration | None:
    if cursor is None:
        return None
    if cursor.row == 0:
        return cursor
    return CursorDeclaration(row=cursor.row + 1, column=cursor.column)


def _footer_text(focus_context: str, *, width: int) -> str:
    if focus_context == "search":
        text = "Type to filter · Enter/↓ to select · ↑ to tabs · Esc to clear"
    elif focus_context in {"settings-list", "model-list"}:
        text = "↑/↓ to move · Enter/Space to select · ↑ on first row to search · q to close"
    elif focus_context == "tabs":
        text = "←/→ to switch tabs · ↓ to enter · q to close"
    else:
        text = "↑ to tabs · q to close"
    return truncate_to_width(text, max_width=width, ellipsis="")


def _manager_bool_config(item_id: str) -> _ManagerBoolConfig | None:
    for config in _MANAGER_BOOL_CONFIGS:
        if config.id == item_id:
            return config
    return None


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _as_bool(value: str) -> bool | None:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _next_value(value: str) -> str:
    current = _as_bool(value)
    if current is None:
        return value
    return _bool_text(not current)


def _next_statusline_value(item_id: str, value: str) -> str:
    if item_id in {
        "statusline.enabled",
        "statusline.field.model",
        "statusline.field.workspace",
        "statusline.field.branch",
        "statusline.field.session",
        "statusline.field.runtime",
    }:
        return _next_value(value)
    if item_id in {"statusline.field.queue", "statusline.field.message"}:
        return {"auto": "true", "true": "false", "false": "auto"}.get(value, value)
    if item_id == "statusline.separator":
        return "dot" if value == "pipe" else "pipe"
    if item_id == "statusline.style":
        return {"codex-like": "muted", "muted": "plain", "plain": "codex-like"}.get(value, value)
    return value


def _is_space_event(event: object) -> bool:
    return (
        getattr(event, "kind", "") == "key"
        and getattr(event, "key", "") == "space"
    ) or (
        getattr(event, "kind", "") == "text"
        and getattr(event, "text", "") == " "
    )


def _is_escape_event(event: object) -> bool:
    return getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"escape", "esc"}


def _is_q_event(event: object) -> bool:
    return (
        getattr(event, "kind", "") == "key"
        and getattr(event, "key", "").casefold() == "q"
    ) or (
        getattr(event, "kind", "") == "text"
        and getattr(event, "text", "").casefold() == "q"
    )


def _is_tab_fallback_key(event: object) -> bool:
    return getattr(event, "kind", "") == "key" and getattr(event, "key", "") in {"left", "right", "home", "end"}
