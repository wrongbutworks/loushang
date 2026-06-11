from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import (
    autowrap_safe_width,
    truncate_to_width,
    visible_width,
)
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import (
    callback_result,
    is_activation_event,
    style_text,
)


@dataclass(frozen=True, slots=True)
class MenuItem:
    value: str
    label: str
    description: str = ""
    disabled: bool = False
    icon: str = ""
    on_select: Callable[[], object] | None = None

    @property
    def display_label(self) -> str:
        return self.label if not self.icon else f"{self.icon} {self.label}".strip()


@dataclass(slots=True)
class Menu:
    items: Sequence[MenuItem]
    active_index: int = 0
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
    _active_index: int = field(default=0, init=False, repr=False)
    _first_visible_index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.items = tuple(self.items)
        self._active_index = self._nearest_enabled_index(self.active_index)

    @property
    def active_value(self) -> str:
        item = self._active_item()
        return "" if item is None else item.value

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = getattr(event, "key", "")
            if key == "up":
                return self._move_active(-1)
            if key == "down":
                return self._move_active(1)
            if key == "home":
                return self._jump_active(first=True)
            if key == "end":
                return self._jump_active(first=False)
        if is_activation_event(event):
            return self._activate()
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        height = max(0, constraints.max_height)
        self._ensure_active_visible(height)
        indexed_items = tuple(enumerate(self.items))
        visible_items = indexed_items[self._first_visible_index : self._first_visible_index + height]
        lines = [RenderLine(_menu_line(self, index, item, target_width)) for index, item in visible_items]
        return RenderResult.from_lines(lines, constraints=constraints)

    def _enabled_indices(self) -> tuple[int, ...]:
        return tuple(index for index, item in enumerate(self.items) if not item.disabled)

    def _nearest_enabled_index(self, preferred: int) -> int:
        enabled = self._enabled_indices()
        if not enabled:
            return 0
        preferred = max(0, min(preferred, len(self.items) - 1))
        if preferred in enabled:
            return preferred
        for index in enabled:
            if index > preferred:
                return index
        return enabled[0]

    def _active_item(self) -> MenuItem | None:
        if not self.items:
            return None
        if self._active_index < 0 or self._active_index >= len(self.items):
            return None
        item = self.items[self._active_index]
        return None if item.disabled else item

    def _move_active(self, delta: int) -> bool | None:
        enabled = self._enabled_indices()
        if not enabled:
            return None
        if self._active_index not in enabled:
            self._active_index = enabled[0]
            return True
        position = enabled.index(self._active_index)
        next_position = position + delta
        if self.wrap:
            next_position %= len(enabled)
        elif next_position < 0 or next_position >= len(enabled):
            return False
        next_index = enabled[next_position]
        if next_index == self._active_index:
            return False
        self._active_index = next_index
        return True

    def _jump_active(self, *, first: bool) -> bool | None:
        enabled = self._enabled_indices()
        if not enabled:
            return None
        target = enabled[0] if first else enabled[-1]
        if target == self._active_index:
            return False
        self._active_index = target
        return True

    def _activate(self) -> object:
        item = self._active_item()
        if item is None:
            return None
        if item.on_select is not None:
            return callback_result(item.on_select())
        return item.value

    def _ensure_active_visible(self, height: int) -> None:
        if height <= 0 or not self.items:
            return
        if self._active_index < self._first_visible_index:
            self._first_visible_index = self._active_index
        elif self._active_index >= self._first_visible_index + height:
            self._first_visible_index = self._active_index - height + 1
        max_first = max(0, len(self.items) - height)
        self._first_visible_index = max(0, min(self._first_visible_index, max_first))


def _menu_line(menu: Menu, index: int, item: MenuItem, target_width: int) -> str:
    is_focused_item = menu.focused and index == menu._active_index and not item.disabled
    prefix = "> " if is_focused_item else "  "
    label = truncate_to_width(f"{prefix}{item.display_label}", max_width=target_width, ellipsis="")
    state_token = (
        "widget.menu.disabled"
        if item.disabled
        else "widget.menu.focus"
        if is_focused_item
        else "widget.menu.item"
    )
    remaining = max(0, target_width - visible_width(label))
    description = ""
    if item.description and remaining >= 3:
        description_text = truncate_to_width(item.description, max_width=remaining - 2, ellipsis="")
        if description_text:
            description = description_text
    rendered = style_text(label, menu.theme, state_token)
    if description:
        rendered = f"{rendered}  {style_text(description, menu.theme, 'widget.menu.description')}"
    return truncate_to_width(rendered, max_width=target_width, ellipsis="")
