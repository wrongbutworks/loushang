from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.fuzzy import fuzzy_match
from loushang.tui.input import InputEvent, InputIntent, InputIntentKind
from loushang.tui.theme import ThemeResolver, ThemeStyle, apply_theme_style
from loushang.tui.ui_parts.text_input import TextInput

DEFAULT_PRIMARY_COLUMN_WIDTH = 32
PRIMARY_COLUMN_GAP = 2
MIN_DESCRIPTION_WIDTH = 10
DEFAULT_SELECTED_STYLE: ThemeStyle = {"color": 33, "bold": True}
TruncateTextHandler = Callable[[str, int, str], str]


@dataclass(frozen=True, slots=True)
class SelectItem:
    label: str
    value: str = ""
    description: str = ""

    @property
    def selected_value(self) -> str:
        return self.value or self.label


SelectionChangeHandler = Callable[[SelectItem | None], None]


@dataclass(slots=True)
class SelectionSurface:
    items: list[SelectItem] | tuple[SelectItem, ...]
    max_visible: int = 5
    select_kind: InputIntentKind = "select"
    empty_text: str = "No matching items"
    selected_index: int = 0
    focused: bool = False
    show_scroll_info: bool = True
    selected_style: ThemeStyle | None = None
    show_selection_when_unfocused: bool = True
    theme: ThemeResolver | None = None
    selected_theme_token: str = "selection.selected"
    enable_search: bool = False
    search_prompt: str = "Search: "
    show_search_when_empty: bool = True
    filter_mode: Literal["prefix", "contains", "fuzzy"] = "prefix"
    on_selection_change: SelectionChangeHandler | None = None
    primary_column_width: int | None = None
    min_description_width: int = MIN_DESCRIPTION_WIDTH
    truncate_text: TruncateTextHandler | None = None
    _filtered_items: list[SelectItem] = field(init=False)
    _filter_input: TextInput | None = field(default=None, init=False, repr=False)
    _last_visible_start: int = field(default=0, init=False, repr=False)
    _last_visible_count: int = field(default=0, init=False, repr=False)
    _last_search_line_count: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._filtered_items = list(self.items)
        self._filter_input = TextInput(prompt=self.search_prompt) if self.enable_search else None
        self.selected_index = _clamp_index(self.selected_index, self._filtered_items)

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def set_filter(self, query: str) -> None:
        if self._filter_input is not None:
            self._filter_input.set_text(query)
        self._apply_filter(query)

    @property
    def filter_text(self) -> str:
        if self._filter_input is None:
            return ""
        return self._filter_input.value

    def handle_input(self, event: InputEvent) -> InputIntent | bool | None:
        if self.enable_search and event.kind == "text":
            filter_input = self._ensure_filter_input()
            filter_input.handle_input(event)
            self._apply_filter(filter_input.value)
            return True
        if event.kind == "mouse":
            self._handle_mouse(event)
            return True
        if event.kind != "key":
            return None
        if self._search_accepts_editing_keys() and _handle_text_input_key(self._filter_input, event.key):
            self._apply_filter(self._filter_input.value if self._filter_input is not None else "")
            return True
        if event.key == "up":
            self._move(-1)
            return True
        if event.key == "down":
            self._move(1)
            return True
        if event.key == "pageUp":
            self._move(-max(1, self.max_visible))
            return True
        if event.key == "pageDown":
            self._move(max(1, self.max_visible))
            return True
        if event.key == "home":
            self._move_to_edge("first")
            return True
        if event.key == "end":
            self._move_to_edge("last")
            return True
        if event.key == "enter":
            selected = self.selected_item()
            if selected is None:
                return True
            return InputIntent(kind=self.select_kind, text=selected.selected_value)
        if event.key in {"esc", "escape"}:
            return InputIntent(kind="surface_close")
        return None

    def selected_item(self) -> SelectItem | None:
        if not self._filtered_items:
            return None
        return self._filtered_items[self.selected_index]

    def render(self, constraints: RenderConstraints) -> RenderResult:
        search_lines: list[RenderLine] = []
        cursor = None
        if self._search_visible():
            filter_input = self._ensure_filter_input()
            search_result = filter_input.render(
                RenderConstraints(
                    width=constraints.width,
                    max_height=1,
                    visible_height=constraints.visible_height,
                )
            )
            search_lines.extend(search_result.lines)
            cursor = search_result.cursor
            if len(search_lines) < constraints.max_height:
                search_lines.append(RenderLine(""))
        self._last_search_line_count = len(search_lines)
        item_height = constraints.max_height - len(search_lines)
        if item_height <= 0:
            self._last_visible_start = 0
            self._last_visible_count = 0
            return RenderResult.from_lines(search_lines[: constraints.max_height], constraints=constraints, cursor=cursor)
        item_result = self._render_items(
            RenderConstraints(
                width=constraints.width,
                max_height=item_height,
                visible_height=constraints.visible_height,
            )
        )
        return RenderResult.from_lines([*search_lines, *item_result.lines], constraints=constraints, cursor=cursor)

    def _render_items(self, constraints: RenderConstraints) -> RenderResult:
        if not self._filtered_items:
            self._last_visible_start = 0
            self._last_visible_count = 0
            line = truncate_to_width(self.empty_text, max_width=autowrap_safe_width(constraints.width))
            return RenderResult.from_lines([RenderLine(line)], constraints=constraints)

        visible_budget = max(1, min(self.max_visible, constraints.max_height))
        include_scroll = self.show_scroll_info and len(self._filtered_items) > visible_budget and constraints.max_height > visible_budget
        item_budget = visible_budget if include_scroll else min(visible_budget, constraints.max_height)
        start = _scroll_start(self.selected_index, len(self._filtered_items), item_budget)
        end = min(start + item_budget, len(self._filtered_items))
        self._last_visible_start = start
        self._last_visible_count = max(0, end - start)

        show_selection = self.focused or self.show_selection_when_unfocused
        lines = [
            RenderLine(
                _render_select_item(
                    self._filtered_items[index],
                    selected=show_selection and index == self.selected_index,
                    width=constraints.width,
                    primary_column_width=self.primary_column_width or _select_primary_column_width(self._filtered_items),
                    min_description_width=self.min_description_width,
                    truncate_text=self.truncate_text,
                    selected_style=self._selected_style(),
                )
            )
            for index in range(start, end)
        ]
        if include_scroll and (start > 0 or end < len(self._filtered_items)):
            info = f"  ({self.selected_index + 1}/{len(self._filtered_items)})"
            lines.append(RenderLine(truncate_to_width(info, max_width=autowrap_safe_width(constraints.width))))
        return RenderResult.from_lines(lines, constraints=constraints)

    def _move(self, delta: int) -> None:
        if not self._filtered_items:
            return
        previous = self.selected_item()
        self.selected_index = (self.selected_index + delta) % len(self._filtered_items)
        if self.selected_item() != previous:
            self._notify_selection_change()

    def _move_to_edge(self, edge: Literal["first", "last"]) -> None:
        if not self._filtered_items:
            return
        previous = self.selected_item()
        self.selected_index = 0 if edge == "first" else len(self._filtered_items) - 1
        if self.selected_item() != previous:
            self._notify_selection_change()

    def _handle_mouse(self, event: InputEvent) -> None:
        if event.mouse_action != "press" or event.mouse_button not in {0, None}:
            return
        if not self._filtered_items or event.mouse_row is None:
            return
        item_row = event.mouse_row - self._last_search_line_count
        if item_row < 0 or item_row >= self._last_visible_count:
            return
        target_index = self._last_visible_start + item_row
        if 0 <= target_index < len(self._filtered_items):
            previous = self.selected_item()
            self.selected_index = target_index
            if self.selected_item() != previous:
                self._notify_selection_change()

    def _ensure_filter_input(self) -> TextInput:
        if self._filter_input is None:
            self._filter_input = TextInput(prompt=self.search_prompt)
        return self._filter_input

    def _search_visible(self) -> bool:
        if not self.enable_search:
            return False
        if self.show_search_when_empty:
            return True
        return bool(self._filter_input is not None and self._filter_input.value)

    def _search_accepts_editing_keys(self) -> bool:
        return self.enable_search and self._search_visible()

    def _apply_filter(self, query: str) -> None:
        normalized = query.lower().strip()
        if not normalized:
            previous = self.selected_item()
            self._filtered_items = list(self.items)
            self.selected_index = _clamp_index(0, self._filtered_items)
            if self.selected_item() != previous:
                self._notify_selection_change()
            return
        previous = self.selected_item()
        self._filtered_items = [
            item
            for item in self.items
            if _select_item_matches_filter(item, normalized, mode=self.filter_mode)
        ]
        self.selected_index = _clamp_index(0, self._filtered_items)
        if self.selected_item() != previous:
            self._notify_selection_change()

    def _selected_style(self) -> ThemeStyle | None:
        if self.selected_style is not None:
            return self.selected_style
        if self.theme is not None and self.selected_theme_token:
            resolved = self.theme.resolve(self.selected_theme_token)
            if resolved:
                return resolved
        return DEFAULT_SELECTED_STYLE

    def _notify_selection_change(self) -> None:
        if self.on_selection_change is not None:
            self.on_selection_change(self.selected_item())


class AutocompleteSurface(SelectionSurface):
    def __init__(self, items: list[SelectItem] | tuple[SelectItem, ...], *, max_visible: int = 5) -> None:
        super().__init__(items=items, max_visible=max_visible, select_kind="complete")


class CommandSurface(SelectionSurface):
    def __init__(
        self,
        items: list[SelectItem] | tuple[SelectItem, ...],
        *,
        query: str = "",
        max_visible: int = 5,
    ) -> None:
        super().__init__(
            items=items,
            max_visible=max_visible,
            select_kind="command",
            enable_search=True,
            show_search_when_empty=False,
            filter_mode="contains",
        )
        if query:
            self.set_filter(query)


@dataclass(slots=True)
class ApprovalSurface:
    action: str
    risk: str = ""
    action_id: str | None = None
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: InputEvent) -> InputIntent | None:
        if event.kind == "text":
            value = event.text.strip().lower()
        elif event.kind == "key":
            value = event.key.lower()
        else:
            return None
        if value == "y":
            return InputIntent(kind="approve", note=self.action_id or "")
        if value == "n" or value in {"esc", "escape"}:
            return InputIntent(kind="reject", note=self.action_id or "")
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        raw_lines = [self.action]
        if self.risk:
            raw_lines.append(self.risk)
        raw_lines.append("[y] approve  [n] reject")
        return _bounded_lines(raw_lines, constraints)


@dataclass(slots=True)
class DialogSurface:
    title: str
    message: str = ""
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: InputEvent) -> InputIntent | None:
        if event.kind != "key":
            return None
        if event.key == "enter":
            return InputIntent(kind="dialog_confirm")
        if event.key in {"esc", "escape"}:
            return InputIntent(kind="dialog_cancel")
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        raw_lines = [self.title]
        if self.message:
            raw_lines.append(self.message)
        raw_lines.append("[enter] confirm  [esc] cancel")
        return _bounded_lines(raw_lines, constraints)


def _render_select_item(
    item: SelectItem,
    *,
    selected: bool,
    width: int,
    primary_column_width: int | None = None,
    min_description_width: int = MIN_DESCRIPTION_WIDTH,
    truncate_text: TruncateTextHandler | None = None,
    selected_style: ThemeStyle | None = None,
) -> str:
    target_width = autowrap_safe_width(width)
    prefix = "> " if selected else "  "
    prefix_width = len(prefix)
    if item.description and target_width > prefix_width + 4:
        description = _normalize_single_line(item.description)
        effective_primary_width = max(1, min(primary_column_width or DEFAULT_PRIMARY_COLUMN_WIDTH, target_width - prefix_width - 4))
        max_primary_width = max(1, effective_primary_width - PRIMARY_COLUMN_GAP)
        label = _truncate_select_text(item.label or item.selected_value, max_primary_width, "", truncate_text)
        spacing = " " * max(1, effective_primary_width - visible_width(label))
        description_start = prefix_width + visible_width(label) + len(spacing)
        remaining_width = target_width - description_start - 2
        if remaining_width > min_description_width:
            line = truncate_to_width(
                prefix + label + spacing + _truncate_select_text(description, remaining_width, "", truncate_text),
                max_width=target_width,
                ellipsis="",
            )
            return _style_selected_line(line, selected=selected, selected_style=selected_style)
    line = truncate_to_width(prefix + item.label, max_width=target_width)
    return _style_selected_line(line, selected=selected, selected_style=selected_style)


def _truncate_select_text(
    text: str,
    max_width: int,
    ellipsis: str,
    truncate_text: TruncateTextHandler | None,
) -> str:
    if truncate_text is not None:
        return truncate_text(text, max_width, ellipsis)
    return truncate_to_width(text, max_width=max_width, ellipsis=ellipsis)


def _select_primary_column_width(items: list[SelectItem]) -> int:
    if not items:
        return DEFAULT_PRIMARY_COLUMN_WIDTH
    widest = max(visible_width(item.label or item.selected_value) + PRIMARY_COLUMN_GAP for item in items)
    return max(1, min(DEFAULT_PRIMARY_COLUMN_WIDTH, max(DEFAULT_PRIMARY_COLUMN_WIDTH, widest)))


def _normalize_single_line(text: str) -> str:
    return " ".join(text.split())


def _select_item_matches_filter(item: SelectItem, query: str, *, mode: Literal["prefix", "contains", "fuzzy"]) -> bool:
    haystacks = (
        item.label.lower(),
        item.selected_value.lower(),
        item.description.lower(),
    )
    if mode == "fuzzy":
        return _fuzzy_matches_any(query, haystacks)
    if mode == "contains":
        return any(query in haystack for haystack in haystacks)
    return any(haystack.startswith(query) for haystack in haystacks[:2])


def _fuzzy_matches_any(query: str, haystacks: tuple[str, ...]) -> bool:
    tokens = tuple(token for token in query.split() if token)
    if not tokens:
        return True
    return all(
        any(fuzzy_match(token, haystack).matches for haystack in haystacks if haystack)
        for token in tokens
    )


def _style_selected_line(line: str, *, selected: bool, selected_style: ThemeStyle | None) -> str:
    if not selected or selected_style is None:
        return line
    return apply_theme_style(line, selected_style)


def _handle_text_input_key(text_input: TextInput | None, key: str) -> bool:
    if text_input is None:
        return False
    return text_input.handle_editing_key(key)


def _scroll_start(selected_index: int, total: int, item_budget: int) -> int:
    if total <= item_budget:
        return 0
    centered = selected_index - item_budget // 2
    return max(0, min(centered, total - item_budget))


def _clamp_index(index: int, items: list[SelectItem]) -> int:
    if not items:
        return 0
    return max(0, min(index, len(items) - 1))


def _bounded_lines(raw_lines: list[str], constraints: RenderConstraints) -> RenderResult:
    target_width = autowrap_safe_width(constraints.width)
    lines = [
        RenderLine(truncate_to_width(line, max_width=target_width))
        for line in raw_lines[: constraints.max_height]
    ]
    return RenderResult.from_lines(lines, constraints=constraints)
