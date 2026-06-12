from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from loushang.tui.cell_width import autowrap_safe_width, truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets._utils import (
    callback_result,
    is_activation_event,
    style_text,
)


@dataclass(frozen=True, slots=True)
class Choice:
    value: str
    label: str
    description: str = ""
    disabled: bool = False


@dataclass(slots=True)
class Checkbox:
    label: str
    checked: bool = False
    description: str = ""
    disabled: bool = False
    on_change: Callable[[bool], object] | None = None
    theme: ThemeResolver | None = None
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if self.disabled or not is_activation_event(event):
            return None
        self.set_checked(not self.checked)
        if self.on_change is None:
            return True
        return callback_result(self.on_change(self.checked))

    def set_checked(self, value: bool) -> None:
        self.checked = value

    def render(self, constraints: RenderConstraints) -> RenderResult:
        marker = "x" if self.checked else " "
        line = f"{_focus_prefix(self.focused)}[{marker}] {self.label}"
        state_token = "widget.disabled" if self.disabled else "widget.focus" if self.focused else None
        return _single_line_result(line, constraints, theme=self.theme, state_token=state_token)


@dataclass(slots=True)
class Toggle:
    label: str
    value: bool = False
    description: str = ""
    disabled: bool = False
    on_change: Callable[[bool], object] | None = None
    theme: ThemeResolver | None = None
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        if self.disabled or not is_activation_event(event):
            return None
        self.value = not self.value
        if self.on_change is None:
            return True
        return callback_result(self.on_change(self.value))

    def render(self, constraints: RenderConstraints) -> RenderResult:
        marker = "on " if self.value else "off"
        line = f"{_focus_prefix(self.focused)}[{marker}] {self.label}"
        state_token = "widget.disabled" if self.disabled else "widget.focus" if self.focused else None
        return _single_line_result(line, constraints, theme=self.theme, state_token=state_token)


@dataclass(slots=True)
class RadioGroup:
    options: list[Choice] | tuple[Choice, ...]
    value: str = ""
    on_change: Callable[[str], object] | None = None
    orientation: Literal["vertical", "horizontal"] = "vertical"
    theme: ThemeResolver | None = None
    focused: bool = False
    _active_index: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._active_index = self._initial_active_index()

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    @property
    def active_value(self) -> str:
        option = self._active_option()
        return option.value if option is not None else ""

    def handle_input(self, event: object) -> object:
        kind = getattr(event, "kind", "")
        key = getattr(event, "key", "")
        if kind == "key" and key in {"up", "down"}:
            self._move_active(-1 if key == "up" else 1)
            return True
        if is_activation_event(event):
            return self._commit_active()
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        if self.orientation == "horizontal":
            return self._render_horizontal(constraints)
        if self.orientation != "vertical":
            raise ValueError("orientation must be 'vertical' or 'horizontal'")
        target_width = autowrap_safe_width(constraints.width)
        lines: list[RenderLine] = []
        for index, option in enumerate(self.options):
            prefix = _focus_prefix(self.focused and index == self._active_index)
            marker = "x" if option.value == self.value else " "
            text = f"{prefix}({marker}) {option.label}"
            if option.description:
                text = f"{text}  {option.description}"
            rendered = truncate_to_width(text, max_width=target_width, ellipsis="")
            state_token = (
                "widget.disabled"
                if option.disabled
                else "widget.focus"
                if self.focused and index == self._active_index
                else None
            )
            lines.append(RenderLine(style_text(rendered, self.theme, state_token)))
            if len(lines) >= constraints.max_height:
                break
        return RenderResult.from_lines(lines, constraints=constraints)

    def _render_horizontal(self, constraints: RenderConstraints) -> RenderResult:
        target_width = autowrap_safe_width(constraints.width)
        segments: list[str] = []
        for index, option in enumerate(self.options):
            prefix = _focus_prefix(self.focused and index == self._active_index)
            marker = "x" if option.value == self.value else " "
            text = f"{prefix}({marker}) {option.label}"
            if option.description:
                text = f"{text}  {option.description}"
            state_token = (
                "widget.disabled"
                if option.disabled
                else "widget.focus"
                if self.focused and index == self._active_index
                else None
            )
            segments.append(style_text(text, self.theme, state_token))
        rendered = truncate_to_width("  ".join(segments), max_width=target_width, ellipsis="")
        return RenderResult.from_lines([RenderLine(rendered)][: constraints.max_height], constraints=constraints)

    def _initial_active_index(self) -> int:
        for index, option in enumerate(self.options):
            if not option.disabled and option.value == self.value:
                return index
        for index, option in enumerate(self.options):
            if not option.disabled:
                return index
        return 0

    def _active_option(self) -> Choice | None:
        if not self.options:
            return None
        return self.options[self._active_index]

    def _move_active(self, delta: int) -> None:
        if not self.options:
            return
        index = self._active_index
        for _ in range(len(self.options)):
            index = (index + delta) % len(self.options)
            if not self.options[index].disabled:
                self._active_index = index
                return

    def _commit_active(self) -> object:
        option = self._active_option()
        if option is None or option.disabled:
            return None
        changed = self.value != option.value
        self.value = option.value
        if self.on_change is None or not changed:
            return True
        return callback_result(self.on_change(self.value))


def _focus_prefix(focused: bool) -> str:
    return "> " if focused else "  "


def _single_line_result(
    line: str,
    constraints: RenderConstraints,
    *,
    theme: ThemeResolver | None = None,
    state_token: str | None = None,
) -> RenderResult:
    target_width = autowrap_safe_width(constraints.width)
    rendered = truncate_to_width(line, max_width=target_width, ellipsis="")
    rendered = style_text(rendered, theme, state_token)
    return RenderResult.from_lines([RenderLine(rendered)][: constraints.max_height], constraints=constraints)
