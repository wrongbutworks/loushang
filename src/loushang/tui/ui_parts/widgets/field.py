from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from loushang.tui.core import RenderConstraints, RenderResult
from loushang.tui.theme import ThemeResolver


@dataclass(slots=True)
class TextField:
    label: str = ""
    value: str = ""
    placeholder: str = ""
    help_text: str = ""
    error: str = ""
    on_submit: Callable[[str], object] | None = None
    on_escape: Callable[[], object] | None = None
    on_change: Callable[[str], object] | None = None
    theme: ThemeResolver | None = None
    focused: bool = False

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: object) -> object:
        return None

    def editor_input_target(self) -> object | None:
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)
