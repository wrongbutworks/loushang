from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
)
from loushang.tui.command_palette import CommandPalette, CommandPaletteItem
from loushang.tui.core import (
    CursorDeclaration,
    RenderConstraints,
    RenderLine,
    RenderResult,
)
from loushang.tui.keybindings import normalize_key_id
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.text_input import TextInput
from loushang.tui.ui_parts.widgets._utils import style_text

__all__ = ["CommandPaletteView"]

_QUERY_LABEL_WIDTH = 14
_FOOTER = "[up/down] command  [enter] run  [esc] close"


@dataclass(slots=True, init=False)
class CommandPaletteView:
    _items: tuple[CommandPaletteItem, ...]
    _title: str
    _query_input: TextInput
    placeholder: str
    max_visible: int
    empty_text: str
    close_on_select: bool
    close_on_cancel: bool
    theme: ThemeResolver | None
    focused: bool
    _active_index: int = field(default=0, init=False, repr=False)
    _first_visible_index: int = field(default=0, init=False, repr=False)

    def __init__(
        self,
        palette: CommandPalette | Sequence[CommandPaletteItem],
        *,
        title: str | None = None,
        placeholder: str = "Search commands",
        query: str = "",
        max_visible: int = 8,
        empty_text: str = "No commands",
        close_on_select: bool = True,
        close_on_cancel: bool = True,
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None:
        if isinstance(palette, CommandPalette):
            self._items = tuple(palette.items)
            self._title = palette.title if title is None else title
        else:
            self._items = tuple(palette)
            self._title = "Command Palette" if title is None else title
        self.placeholder = placeholder
        self.max_visible = max(1, max_visible)
        self.empty_text = empty_text
        self.close_on_select = close_on_select
        self.close_on_cancel = close_on_cancel
        self.theme = theme
        self.focused = focused
        self._active_index = 0
        self._first_visible_index = 0
        self._query_input = TextInput(placeholder=placeholder, theme=theme, focused=focused)
        self._query_input.set_text(query)
        self._repair_active(previous_value="")

    @property
    def title(self) -> str:
        return self._title

    @property
    def query(self) -> str:
        return self._query_input.value

    @property
    def filtered_items(self) -> tuple[CommandPaletteItem, ...]:
        needle = self.query.casefold().strip()
        if not needle:
            return self._items
        return tuple(item for item in self._items if _matches(item, needle))

    @property
    def active_value(self) -> str:
        item = self._active_item()
        return "" if item is None else item.value

    def set_query(self, query: str) -> None:
        previous_value = self.active_value
        self._query_input.set_text(query)
        self._repair_active(previous_value=previous_value)

    def focus(self) -> None:
        self.focused = True
        self._query_input.focus()

    def blur(self) -> None:
        self.focused = False
        self._query_input.blur()

    def editor_input_target(self) -> object | None:
        if not self.focused:
            return None
        return self._query_input.editor_input_target()

    def handle_input(self, event: object) -> object:
        kind = getattr(event, "kind", "")
        if kind in {"text", "paste"}:
            before = self.query
            previous_value = self.active_value
            handled = self._query_input.handle_input(event)
            if handled and self.query != before:
                self._repair_active(previous_value=previous_value)
            return handled or None
        if kind != "key":
            return None
        key = normalize_key_id(getattr(event, "key", ""))
        if key in {"escape", "esc", "ctrl+c"}:
            return self._cancel()
        if key == "enter":
            return self._select_active()
        if key == "up":
            return self._move_active(-1)
        if key == "down":
            return self._move_active(1)
        if key == "ctrl+home":
            return self._jump_active(first=True)
        if key == "ctrl+end":
            return self._jump_active(first=False)
        before = self.query
        previous_value = self.active_value
        handled = self._query_input.handle_editing_key(key)
        if handled and self.query != before:
            self._repair_active(previous_value=previous_value)
        return True if handled else None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        if constraints.max_height <= 0:
            return RenderResult.from_lines([], constraints=constraints)

        lines: list[RenderLine] = []
        cursor: CursorDeclaration | None = None

        if self.title:
            lines.append(self._title_line(target_width))
            if len(lines) + 1 < constraints.max_height:
                lines.append(RenderLine(""))

        query_row = len(lines)
        if len(lines) < constraints.max_height:
            query_line, query_cursor_column = self._query_line(target_width)
            lines.append(query_line)
            if self.focused:
                cursor = CursorDeclaration(row=query_row, column=query_cursor_column)

        if len(lines) + 2 <= constraints.max_height:
            lines.append(RenderLine(""))
        if len(lines) + 2 <= constraints.max_height:
            lines.append(self._section_line(target_width))

        remaining = constraints.max_height - len(lines)
        if remaining > 0:
            result_budget = min(self.max_visible, remaining)
            result_lines = self._result_lines(target_width, result_budget)
            lines.extend(result_lines)

        if len(lines) < constraints.max_height:
            lines.append(self._footer_line(target_width))

        return RenderResult.from_lines(lines[: constraints.max_height], constraints=constraints, cursor=cursor)
        return None

    def _active_item(self) -> CommandPaletteItem | None:
        items = self.filtered_items
        if self._active_index < 0 or self._active_index >= len(items):
            return None
        item = items[self._active_index]
        return None if item.disabled else item

    def _enabled_indices(self, items: tuple[CommandPaletteItem, ...]) -> tuple[int, ...]:
        return tuple(index for index, item in enumerate(items) if not item.disabled)

    def _repair_active(self, *, previous_value: str = "") -> None:
        items = self.filtered_items
        enabled = self._enabled_indices(items)
        if not enabled:
            self._active_index = 0
            self._first_visible_index = 0
            return
        if previous_value:
            for index in enabled:
                if items[index].value == previous_value:
                    self._active_index = index
                    return
        self._active_index = enabled[0]
        self._first_visible_index = min(self._first_visible_index, max(0, len(items) - 1))

    def _move_active(self, delta: int) -> bool | None:
        items = self.filtered_items
        enabled = self._enabled_indices(items)
        if not enabled:
            return None
        if self._active_index not in enabled:
            self._active_index = enabled[0]
            return True
        position = enabled.index(self._active_index)
        next_position = position + delta
        if next_position < 0 or next_position >= len(enabled):
            return False
        next_index = enabled[next_position]
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        return True

    def _jump_active(self, *, first: bool) -> bool | None:
        items = self.filtered_items
        enabled = self._enabled_indices(items)
        if not enabled:
            return None
        next_index = enabled[0] if first else enabled[-1]
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        return True

    def _select_active(self) -> object:
        item = self._active_item()
        if item is None:
            return None
        from loushang.tui.input import InputIntent

        select = InputIntent(kind="command_select", text=item.value, note=item.display_label())
        if not self.close_on_select:
            return select
        return (select, InputIntent(kind="surface_close"))

    def _cancel(self) -> object:
        from loushang.tui.input import InputIntent

        cancel = InputIntent(kind="command_cancel")
        if not self.close_on_cancel:
            return cancel
        return (cancel, InputIntent(kind="surface_close"))

    def _title_line(self, width: int) -> RenderLine:
        text = truncate_to_width(self.title, max_width=width, ellipsis="")
        return RenderLine(style_text(text, self.theme, "widget.commandPalette.title"))

    def _query_line(self, width: int) -> tuple[RenderLine, int]:
        label_width = min(_QUERY_LABEL_WIDTH, width)
        label = truncate_to_width("Search".ljust(label_width), max_width=label_width, ellipsis="")
        input_width = max(0, width - label_width)
        input_text = ""
        input_cursor_column = 0
        if input_width > 0:
            query_result = self._query_input.render(RenderConstraints(width=input_width, max_height=1))
            if query_result.lines:
                input_text = query_result.lines[0].text
            if query_result.cursor is not None:
                input_cursor_column = query_result.cursor.column
        query_token = "widget.commandPalette.queryText" if self.query else "widget.commandPalette.placeholder"
        line = (
            f"{style_text(label, self.theme, 'widget.commandPalette.queryLabel')}"
            f"{style_text(input_text, self.theme, query_token)}"
        )
        line = truncate_to_width(line, max_width=width, ellipsis="")
        cursor_column = min(visible_width(label) + input_cursor_column, visible_width(line))
        return RenderLine(line), cursor_column

    def _section_line(self, width: int) -> RenderLine:
        text = truncate_to_width("Results", max_width=width, ellipsis="")
        return RenderLine(style_text(text, self.theme, "widget.commandPalette.section"))

    def _result_lines(self, width: int, height: int) -> list[RenderLine]:
        items = self.filtered_items
        if not items:
            text = truncate_to_width(self.empty_text, max_width=width, ellipsis="")
            return [RenderLine(style_text(text, self.theme, "widget.commandPalette.empty"))]
        self._ensure_active_visible(height)
        start = self._first_visible_index
        end = min(start + height, len(items))
        return [RenderLine(_item_line(self, index, item, width)) for index, item in enumerate(items[start:end], start)]

    def _footer_line(self, width: int) -> RenderLine:
        text = truncate_to_width(_FOOTER, max_width=width, ellipsis="")
        return RenderLine(style_text(text, self.theme, "widget.commandPalette.footer"))

    def _ensure_active_visible(self, height: int) -> None:
        items = self.filtered_items
        if height <= 0 or not items:
            return
        if self._active_index < self._first_visible_index:
            self._first_visible_index = self._active_index
        elif self._active_index >= self._first_visible_index + height:
            self._first_visible_index = self._active_index - height + 1
        max_first = max(0, len(items) - height)
        self._first_visible_index = max(0, min(self._first_visible_index, max_first))


def _matches(item: CommandPaletteItem, needle: str) -> bool:
    return any(
        needle in value.casefold()
        for value in (item.value, item.display_label(), item.description)
    )


def _item_line(view: CommandPaletteView, index: int, item: CommandPaletteItem, width: int) -> str:
    is_focused_item = view.focused and index == view._active_index and not item.disabled
    prefix = "> " if is_focused_item else "  "
    label = truncate_to_width(f"{prefix}{item.display_label()}", max_width=width, ellipsis="")
    item_token = (
        "widget.commandPalette.disabled"
        if item.disabled
        else "widget.commandPalette.focus"
        if is_focused_item
        else "widget.commandPalette.item"
    )
    remaining = max(0, width - visible_width(label))
    description = ""
    if item.description and remaining >= 3:
        description = truncate_to_width(item.description, max_width=remaining - 2, ellipsis="")
    rendered = style_text(label, view.theme, item_token)
    if description:
        rendered = f"{rendered}  {style_text(description, view.theme, 'widget.commandPalette.description')}"
    return truncate_to_width(rendered, max_width=width, ellipsis="")
