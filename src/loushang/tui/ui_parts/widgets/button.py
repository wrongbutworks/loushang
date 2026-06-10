from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from loushang.tui.core import RenderConstraints, RenderResult
from loushang.tui.theme import ThemeResolver

ButtonKind = Literal["default", "primary", "danger", "ghost"]


@dataclass(slots=True)
class Button:
    label: str
    icon: str = ""
    kind: ButtonKind = "default"
    disabled: bool = False
    on_press: Callable[[], object] | None = None
    theme: ThemeResolver | None = None
    theme_token: str | None = None
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)


def IconButton(icon: str, *, label: str = "", **kwargs: object) -> Button:
    return Button(label=label, icon=icon, **kwargs)
