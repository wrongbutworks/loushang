from __future__ import annotations

from dataclasses import dataclass

from loushang.tui.core import RenderConstraints, RenderResult
from loushang.tui.theme import ThemeResolver


@dataclass(slots=True)
class SelectList:
    items: list[object] | tuple[object, ...]
    max_visible: int = 5
    close_on_escape: bool = False
    theme: ThemeResolver | None = None
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    @property
    def selected_value(self) -> str:
        return ""

    def handle_input(self, event: object) -> object:
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)
