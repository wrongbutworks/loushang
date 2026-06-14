from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import (
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
)
from loushang.tui.keybindings import normalize_key_id
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.text_input import TextInput
from loushang.tui.ui_parts.widgets._utils import callback_result, style_text

__all__ = ["SearchableList", "SearchableListItem", "SearchableListSelect"]


@dataclass(frozen=True, slots=True)
class SearchableListItem:
    key: str
    label: str
    value: str = ""
    description: str = ""
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class SearchableListSelect:
    key: str
    label: str
    value: str = ""


@dataclass(slots=True, init=False)
class SearchableList:
    _items: tuple[SearchableListItem, ...]
    _query_input: TextInput
    _active_index: int = field(default=0, init=False, repr=False)
    _scroll_offset: int = field(default=0, init=False, repr=False)
    _last_visible_count: int = field(default=0, init=False, repr=False)
    focus_region: str
    placeholder: str
    empty_text: str
    on_select: Callable[[SearchableListItem], object] | None
    theme: ThemeResolver | None
    focused: bool
    search_box: bool
    detail_column: int | None
    column_headers: tuple[str, str] | None
    footer_hint: str

    def __init__(
        self,
        items: Sequence[SearchableListItem],
        *,
        query: str = "",
        active_index: int = 0,
        focus_region: str = "search",
        placeholder: str = "Search",
        empty_text: str = "No matching items",
        on_select: Callable[[SearchableListItem], object] | None = None,
        theme: ThemeResolver | None = None,
        focused: bool = False,
        search_box: bool = False,
        detail_column: int | None = None,
        column_headers: tuple[str, str] | None = None,
        footer_hint: str = "",
    ) -> None:
        self._items = tuple(items)
        self.placeholder = placeholder
        self.empty_text = empty_text
        self.on_select = on_select
        self.theme = theme
        self.focused = focused
        self.search_box = search_box
        self.detail_column = detail_column
        self.column_headers = column_headers
        self.footer_hint = footer_hint
        self.focus_region = focus_region if focus_region in {"search", "list"} else "search"
        self._active_index = max(0, active_index)
        self._scroll_offset = 0
        self._last_visible_count = 0
        self._query_input = TextInput(
            placeholder=placeholder,
            theme=theme,
            focused=focused and self.focus_region == "search",
        )
        self._query_input.set_text(query)
        self._repair_active(previous_key="")

    @property
    def query(self) -> str:
        return self._query_input.value

    @property
    def filtered_items(self) -> tuple[SearchableListItem, ...]:
        needle = self.query.casefold().strip()
        if not needle:
            return self._items
        return tuple(item for item in self._items if _matches(item, needle))

    @property
    def active_item(self) -> SearchableListItem | None:
        items = self.filtered_items
        if self._active_index < 0 or self._active_index >= len(items):
            return None
        item = items[self._active_index]
        return None if item.disabled else item

    @property
    def active_key(self) -> str:
        item = self.active_item
        return "" if item is None else item.key

    @property
    def scroll_offset(self) -> int:
        return self._scroll_offset

    @property
    def more_above(self) -> int:
        return max(0, self._scroll_offset)

    @property
    def more_below(self) -> int:
        return max(0, len(self.filtered_items) - (self._scroll_offset + self._last_visible_count))

    def set_query(self, query: str) -> None:
        previous_key = self.active_key
        self._query_input.set_text(query)
        self._repair_active(previous_key=previous_key)

    def set_items(self, items: Sequence[SearchableListItem], *, preserve_active_key: str = "") -> None:
        previous_key = preserve_active_key or self.active_key
        self._items = tuple(items)
        self._repair_active(previous_key=previous_key)
        if self.focus_region == "list" and self.active_item is None:
            self.focus_search()

    def focus(self) -> None:
        self.focused = True
        self.focus_search()

    def blur(self) -> None:
        self.focused = False
        self._query_input.blur()

    def focus_search(self) -> None:
        self.focus_region = "search"
        self._query_input.focus()

    def focus_list(self) -> bool:
        if self.active_item is None:
            return False
        self.focus_region = "list"
        self._query_input.blur()
        return True

    def editor_input_target(self) -> object | None:
        if not self.focused or self.focus_region != "search":
            return None
        return self._query_input.editor_input_target()

    def handle_input(self, event: object) -> object:
        if self.focus_region == "search":
            return self._handle_search_input(event)
        if self.focus_region == "list":
            return self._handle_list_input(event)
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        lines: list[RenderLine] = []
        cursor: CursorDeclaration | None = None
        query_line, query_cursor_column = self._query_line(target_width)
        if self.search_box:
            lines.extend(_boxed_query_lines(query_line.text, target_width, self.theme))
            query_cursor_row = 1
            query_cursor_column += 2
        else:
            lines.append(query_line)
            query_cursor_row = 0
        if self.focused and self.focus_region == "search":
            cursor = CursorDeclaration(row=query_cursor_row, column=query_cursor_column)

        if self.column_headers is not None and len(lines) < constraints.max_height:
            lines.append(_column_header_line(self, target_width))

        remaining_height = max(0, constraints.max_height - len(lines))
        footer_reserved = 1 if self.footer_hint and remaining_height >= 2 else 0
        item_height = max(0, remaining_height - footer_reserved)
        if item_height > 0:
            lines.extend(self._result_lines(target_width, item_height))
        else:
            self._last_visible_count = 0
        if footer_reserved and len(lines) < constraints.max_height:
            lines.append(_footer_hint_line(self, target_width))

        return RenderResult.from_lines(lines[: constraints.max_height], constraints=constraints, cursor=cursor)

    def _handle_search_input(self, event: object) -> object:
        kind = getattr(event, "kind", "")
        if kind in {"text", "paste"}:
            before = self.query
            previous_key = self.active_key
            handled = self._query_input.handle_input(event)
            if handled and self.query != before:
                self._repair_active(previous_key=previous_key)
            return handled or None
        if kind != "key":
            return None
        key = normalize_key_id(getattr(event, "key", ""))
        if key == "down":
            return True if self.focus_list() else None
        if key == "enter":
            return self._select_active()
        if key == "escape" and self.query:
            self.set_query("")
            return True
        if key == "up":
            return None
        before = self.query
        previous_key = self.active_key
        handled = self._query_input.handle_editing_key(key)
        if handled and self.query != before:
            self._repair_active(previous_key=previous_key)
        return True if handled else None

    def _handle_list_input(self, event: object) -> object:
        kind = getattr(event, "kind", "")
        if kind == "text" and getattr(event, "text", "") == " ":
            return self._select_active()
        if kind != "key":
            return None
        key = normalize_key_id(getattr(event, "key", ""))
        if key == "up" and self._at_first_enabled_item():
            self.focus_search()
            return True
        if key == "up":
            return self._move_active(-1)
        if key == "down":
            return self._move_active(1)
        if key == "pageUp":
            return self._move_active(-max(1, self._last_visible_count))
        if key == "pageDown":
            return self._move_active(max(1, self._last_visible_count))
        if key == "home":
            return self._jump_active(first=True)
        if key == "end":
            return self._jump_active(first=False)
        if key in {"enter", "space"}:
            return self._select_active()
        return None

    def _query_line(self, width: int) -> tuple[RenderLine, int]:
        query_result = self._query_input.render(RenderConstraints(width=width, max_height=1))
        text = query_result.lines[0].text if query_result.lines else ""
        token = "widget.searchableList.search" if self.query else "widget.searchableList.placeholder"
        line = truncate_to_width(style_text(text, self.theme, token), max_width=width, ellipsis="")
        cursor_column = 0
        if query_result.cursor is not None:
            cursor_column = min(query_result.cursor.column, visible_width(line))
        return RenderLine(line), cursor_column

    def _result_lines(self, width: int, height: int) -> list[RenderLine]:
        items = self.filtered_items
        if not items:
            self._scroll_offset = 0
            self._last_visible_count = 0
            text = truncate_to_width(self.empty_text, max_width=width, ellipsis="")
            return [RenderLine(style_text(text, self.theme, "widget.searchableList.empty"))]

        item_budget = height
        needs_overflow = len(items) > item_budget
        if needs_overflow and item_budget > 1:
            item_budget -= 1
        item_budget = max(1, item_budget)
        self._ensure_active_visible(item_budget)
        start = self._scroll_offset
        end = min(start + item_budget, len(items))
        self._last_visible_count = max(0, end - start)
        lines = [RenderLine(_item_line(self, index, item, width)) for index, item in enumerate(items[start:end], start)]
        overflow = _overflow_line(self, width)
        if overflow is not None and len(lines) < height:
            lines.append(overflow)
        return lines[:height]

    def _repair_active(self, *, previous_key: str = "") -> None:
        items = self.filtered_items
        enabled = _enabled_indices(items)
        if not enabled:
            self._active_index = 0
            self._scroll_offset = 0
            self._last_visible_count = 0
            return
        if previous_key:
            for index in enabled:
                if items[index].key == previous_key:
                    self._active_index = index
                    self._scroll_offset = min(self._scroll_offset, max(0, len(items) - 1))
                    return
        self._active_index = enabled[0]
        self._scroll_offset = min(self._scroll_offset, max(0, len(items) - 1))

    def _move_active(self, delta: int) -> bool | None:
        items = self.filtered_items
        enabled = _enabled_indices(items)
        if not enabled:
            return None
        if self._active_index not in enabled:
            self._active_index = enabled[0]
            self._ensure_active_visible(max(1, self._last_visible_count))
            return True
        position = enabled.index(self._active_index)
        next_position = position + delta
        if next_position < 0 or next_position >= len(enabled):
            return False
        next_index = enabled[next_position]
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        self._ensure_active_visible(max(1, self._last_visible_count))
        return True

    def _jump_active(self, *, first: bool) -> bool | None:
        items = self.filtered_items
        enabled = _enabled_indices(items)
        if not enabled:
            return None
        next_index = enabled[0] if first else enabled[-1]
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        self._ensure_active_visible(max(1, self._last_visible_count))
        return True

    def _at_first_enabled_item(self) -> bool:
        enabled = _enabled_indices(self.filtered_items)
        return bool(enabled) and self._active_index == enabled[0]

    def _ensure_active_visible(self, height: int) -> None:
        items = self.filtered_items
        if height <= 0 or not items:
            self._scroll_offset = 0
            self._last_visible_count = 0
            return
        if self._active_index < self._scroll_offset:
            self._scroll_offset = self._active_index
        elif self._active_index >= self._scroll_offset + height:
            self._scroll_offset = self._active_index - height + 1
        max_first = max(0, len(items) - height)
        self._scroll_offset = max(0, min(self._scroll_offset, max_first))

    def _select_active(self) -> object:
        item = self.active_item
        if item is None:
            return None
        if self.on_select is not None:
            return callback_result(self.on_select(item))
        return SearchableListSelect(item.key, item.label, item.value)


def _enabled_indices(items: tuple[SearchableListItem, ...]) -> tuple[int, ...]:
    return tuple(index for index, item in enumerate(items) if not item.disabled)


def _matches(item: SearchableListItem, needle: str) -> bool:
    return needle in item.key.casefold() or needle in item.label.casefold()


def _item_line(view: SearchableList, index: int, item: SearchableListItem, width: int) -> str:
    is_focused_item = view.focused and view.focus_region == "list" and index == view._active_index and not item.disabled
    prefix = "> " if is_focused_item else "  "
    item_token = (
        "widget.searchableList.disabled"
        if item.disabled
        else "widget.searchableList.focus"
        if is_focused_item
        else "widget.searchableList.item"
    )
    detail = item.value or item.description
    if view.detail_column is not None and detail:
        detail_column = max(4, min(view.detail_column, max(4, width - 1)))
        label = truncate_to_width(f"{prefix}{item.label}", max_width=detail_column, ellipsis="")
        rendered = style_text(label, view.theme, item_token)
        padding = " " * max(1, detail_column - visible_width(label))
        detail_text = truncate_to_width(detail, max_width=max(0, width - detail_column), ellipsis="")
        if detail_text:
            rendered = f"{rendered}{padding}{style_text(detail_text, view.theme, 'widget.searchableList.description')}"
        return truncate_to_width(rendered, max_width=width, ellipsis="")

    label = truncate_to_width(f"{prefix}{item.label}", max_width=width, ellipsis="")
    remaining = max(0, width - visible_width(label))
    rendered = style_text(label, view.theme, item_token)
    if detail and remaining >= 3:
        detail_text = truncate_to_width(detail, max_width=remaining - 2, ellipsis="")
        if detail_text:
            rendered = f"{rendered}  {style_text(detail_text, view.theme, 'widget.searchableList.description')}"
    return truncate_to_width(rendered, max_width=width, ellipsis="")


def _column_header_line(view: SearchableList, width: int) -> RenderLine:
    if view.column_headers is None:
        return RenderLine("")
    label_header, detail_header = view.column_headers
    if view.detail_column is not None and detail_header:
        detail_column = max(4, min(view.detail_column, max(4, width - 1)))
        label = truncate_to_width(label_header, max_width=detail_column, ellipsis="")
        padding = " " * max(1, detail_column - visible_width(label))
        detail = truncate_to_width(detail_header, max_width=max(0, width - detail_column), ellipsis="")
        text = truncate_to_width(f"{label}{padding}{detail}", max_width=width, ellipsis="")
    else:
        parts = label_header if not detail_header else f"{label_header}  {detail_header}"
        text = truncate_to_width(parts, max_width=width, ellipsis="")
    return RenderLine(style_text(text, view.theme, "widget.searchableList.header"))


def _overflow_line(view: SearchableList, width: int) -> RenderLine | None:
    parts: list[str] = []
    if view.more_above:
        parts.append(f"↑ {view.more_above} more above")
    if view.more_below:
        parts.append(f"↓ {view.more_below} more below")
    if not parts:
        return None
    text = truncate_to_width(f"  {' / '.join(parts)}", max_width=width, ellipsis="")
    return RenderLine(style_text(text, view.theme, "widget.searchableList.overflow"))


def _footer_hint_line(view: SearchableList, width: int) -> RenderLine:
    text = truncate_to_width(view.footer_hint, max_width=width, ellipsis="")
    return RenderLine(style_text(text, view.theme, "widget.searchableList.footer"))


def _boxed_query_lines(text: str, width: int, theme: ThemeResolver | None) -> list[RenderLine]:
    if width <= 0:
        return []
    if width < 4:
        return [RenderLine(truncate_to_width(text, max_width=width, ellipsis=""))]
    inner_width = max(0, width - 4)
    visible_text = truncate_to_width(text, max_width=inner_width, ellipsis="")
    padding = " " * max(0, inner_width - visible_width(visible_text))
    top = "╭" + "─" * (width - 2) + "╮"
    bottom = "╰" + "─" * (width - 2) + "╯"
    left = style_text("│ ", theme, "widget.searchableList.box")
    right = style_text(" │", theme, "widget.searchableList.box")
    return [
        RenderLine(style_text(top, theme, "widget.searchableList.box")),
        RenderLine(f"{left}{visible_text}{padding}{right}"),
        RenderLine(style_text(bottom, theme, "widget.searchableList.box")),
    ]
