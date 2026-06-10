from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import (
    callback_result,
    is_activation_event,
    style_text,
)


@dataclass(frozen=True, slots=True)
class ToolbarAction:
    label: str
    on_press: Callable[[], object] | None = None
    disabled: bool = False
    icon: str = ""
    value: str = ""

    @property
    def display_label(self) -> str:
        return self.label if not self.icon else f"{self.icon} {self.label}".strip()


@dataclass(slots=True)
class Toolbar:
    actions: Sequence[ToolbarAction]
    active_index: int = 0
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
    _active_index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.actions = tuple(self.actions)
        self._active_index = self._nearest_enabled_index(self.active_index)

    @property
    def active_value(self) -> str:
        action = self._active_action()
        if action is None:
            return ""
        return action.value or action.label

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if getattr(event, "kind", "") == "key":
            key = getattr(event, "key", "")
            if key == "left":
                return self._move_active(-1)
            if key == "right":
                return self._move_active(1)
            if key == "home":
                return self._jump_active(first=True)
            if key == "end":
                return self._jump_active(first=False)
        if is_activation_event(event):
            return self._activate()
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if not self.actions:
            return RenderResult.from_lines([], constraints=constraints)
        target_width = autowrap_safe_width(constraints.width)
        parts: list[str] = []
        for index, action in enumerate(self.actions):
            is_focused_action = self.focused and index == self._active_index and not action.disabled
            prefix = "> " if is_focused_action else ""
            text = f"{prefix}[{action.display_label}]"
            token = (
                "widget.toolbar.disabled"
                if action.disabled
                else "widget.toolbar.focus"
                if is_focused_action
                else "widget.toolbar.action"
            )
            parts.append(style_text(text, self.theme, token))
        line = truncate_to_width("  ".join(parts), max_width=target_width, ellipsis="")
        return RenderResult.from_lines([RenderLine(line)][: constraints.max_height], constraints=constraints)

    def _enabled_indices(self) -> tuple[int, ...]:
        return tuple(index for index, action in enumerate(self.actions) if not action.disabled)

    def _nearest_enabled_index(self, preferred: int) -> int:
        enabled = self._enabled_indices()
        if not enabled:
            return 0
        preferred = max(0, min(preferred, len(self.actions) - 1))
        if preferred in enabled:
            return preferred
        for index in enabled:
            if index > preferred:
                return index
        return enabled[0]

    def _active_action(self) -> ToolbarAction | None:
        if not self.actions:
            return None
        if self._active_index < 0 or self._active_index >= len(self.actions):
            return None
        action = self.actions[self._active_index]
        return None if action.disabled else action

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
        action = self._active_action()
        if action is None:
            return None
        if action.on_press is not None:
            return callback_result(action.on_press())
        if action.value:
            return action.value
        return True
