from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from loushang.tui.core import RenderConstraints, RenderResult
from loushang.tui.theme import ThemeResolver


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
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)


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
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)


@dataclass(slots=True)
class RadioGroup:
    options: list[Choice] | tuple[Choice, ...]
    value: str = ""
    on_change: Callable[[str], object] | None = None
    theme: ThemeResolver | None = None
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    @property
    def active_value(self) -> str:
        return self.value

    def handle_input(self, event: object) -> object:
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)
